"""
Utility functions for handling images in the image-to-product-info program.
"""

import base64
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from PIL import Image
import io


def get_image_size_mb(image_path: Path) -> float:
    """Get image file size in MB."""
    return image_path.stat().st_size / (1024 * 1024)


def get_image_resolution(image_path: Path) -> tuple[int, int]:
    """Get image resolution (width, height)."""
    with Image.open(image_path) as img:
        return img.size


def get_total_pixels(image_path: Path) -> int:
    """Get total number of pixels in the image."""
    width, height = get_image_resolution(image_path)
    return width * height


def downsample_image(image_path: Path, max_size_mb: float = 3.5, max_pixels: int = 33000000) -> bytes:
    """
    Downsample image to meet size and resolution limits.
    
    Args:
        image_path: Path to the image file
        max_size_mb: Maximum file size in MB (default 3.5MB to stay under 4MB base64 limit)
        max_pixels: Maximum total pixels (33 megapixels per Groq docs)
        
    Returns:
        Bytes of the downsampled image
    """
    with Image.open(image_path) as img:
        # Convert to RGB if necessary (removes alpha channel, reduces size)
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Check and reduce resolution if needed
        width, height = img.size
        total_pixels = width * height
        
        if total_pixels > max_pixels:
            # Calculate scale factor to get under pixel limit
            scale_factor = (max_pixels / total_pixels) ** 0.5
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save to bytes and check size, reduce quality if needed
        output = io.BytesIO()
        quality = 95
        
        while True:
            output.seek(0)
            output.truncate(0)
            img.save(output, format='JPEG', quality=quality, optimize=True)
            size_mb = len(output.getvalue()) / (1024 * 1024)
            
            if size_mb <= max_size_mb or quality <= 50:
                break
            
            quality -= 10
        
        return output.getvalue()


def encode_image_to_base64(image_path: Path, downsample_if_needed: bool = True, max_size_mb: float = 3.5) -> str:
    """
    Encode an image file to base64 string with proper data URI format.
    
    Handles Groq API limits:
    - Maximum 4MB for base64 encoded images
    - Maximum 33 megapixels per image
    - Maximum 5 images per request
    
    Args:
        image_path: Path to the image file
        downsample_if_needed: Whether to downsample if image exceeds limits
        max_size_mb: Maximum size per image in MB (default 3.5MB, can be reduced when sending multiple images)
        
    Returns:
        Base64 encoded image string with data URI prefix (e.g., "data:image/jpeg;base64,...")
    """
    image_path = Path(image_path)
    
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    # Determine image format
    with Image.open(image_path) as img:
        format_map = {
            'JPEG': 'jpeg',
            'PNG': 'png',
            'GIF': 'gif',
            'WEBP': 'webp',
            'BMP': 'bmp'
        }
        image_format = format_map.get(img.format, 'jpeg')
    
    # Check if downsampling is needed
    file_size_mb = get_image_size_mb(image_path)
    total_pixels = get_total_pixels(image_path)
    
    # max_size_mb is passed as parameter (can be reduced for multiple images)
    max_pixels = 33000000  # 33 megapixels per Groq docs
    
    # Base64 encoding adds ~33% overhead, so check if original file * 1.33 exceeds limit
    estimated_base64_size_mb = file_size_mb * 1.33
    
    if downsample_if_needed and (estimated_base64_size_mb > max_size_mb or total_pixels > max_pixels):
        image_bytes = downsample_image(image_path, max_size_mb=max_size_mb, max_pixels=max_pixels)
        # After downsampling, we always save as JPEG
        image_format = 'jpeg'
    else:
        # Read original file
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        # Double-check base64 size after encoding (safety check)
        # Account for base64 overhead (~33% increase)
        base64_size_mb = (len(image_bytes) * 4 / 3) / (1024 * 1024)
        if base64_size_mb > max_size_mb:
            # If base64 size exceeds limit, downsample
            image_bytes = downsample_image(image_path, max_size_mb=max_size_mb, max_pixels=max_pixels)
            image_format = 'jpeg'
    
    # Encode to base64
    base64_string = base64.b64encode(image_bytes).decode('utf-8')
    
    # Return with data URI prefix
    return f"data:image/{image_format};base64,{base64_string}"


def get_image_url(image_path: Path, base_url: str, relative_to: Path) -> str:
    """
    Generate URL for an image file.
    
    Args:
        image_path: Absolute path to the image file
        base_url: Base URL for serving images (e.g., "http://localhost:8000/api/image")
        relative_to: Base path to calculate relative path from
        
    Returns:
        Full URL to the image (e.g., "http://localhost:8000/api/image/product_001/image.jpg")
    """
    image_path = Path(image_path)
    relative_to = Path(relative_to)
    
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    rel_path = image_path.relative_to(relative_to)
    # URL-encode each path component, then join with /
    encoded_parts = [quote(part, safe='') for part in rel_path.parts]
    encoded_path = '/'.join(encoded_parts)
    
    # Remove trailing slash from base_url if present
    base_url = base_url.rstrip('/')
    
    return f"{base_url}/{encoded_path}"

