"""
LLM pricing lookup from hierarchical YAML configuration.
Supports model names like "groq/openai/gpt-oss-20b" and "cerebras/gpt-oss-120b".
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import yaml

@dataclass
class ModelPricing:
    input_price_per_million: float
    output_price_per_million: float

# Load pricing at module import
_PRICING_FILE = Path(__file__).parent / "llm_pricing.yaml"
_PRICING_DATA = yaml.safe_load(_PRICING_FILE.read_text())


def get_pricing(model_name: str) -> Optional[ModelPricing]:
    """
    Get pricing by navigating YAML hierarchy.

    Args:
        model_name: e.g., "groq/openai/gpt-oss-20b" or "cerebras/gpt-oss-120b"

    Returns:
        ModelPricing if found, None otherwise
    """
    parts = model_name.split("/")
    node = _PRICING_DATA

    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]

    if isinstance(node, dict) and "input" in node and "output" in node:
        return ModelPricing(
            input_price_per_million=node["input"],
            output_price_per_million=node["output"]
        )
    return None


def get_provider_source(provider: str) -> Optional[str]:
    """Get the source URL for a provider's pricing page."""
    if provider in _PRICING_DATA and "_source" in _PRICING_DATA[provider]:
        return _PRICING_DATA[provider]["_source"]
    return None


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """
    Calculate the cost for a given model and token usage.

    Args:
        model_name: The name of the model
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Total cost in USD, or None if model pricing is not found
    """
    pricing = get_pricing(model_name)
    if pricing is None:
        return None

    input_cost = (input_tokens / 1_000_000) * pricing.input_price_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_price_per_million
    return input_cost + output_cost
