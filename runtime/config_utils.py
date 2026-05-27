"""
Utility module for handling experiment configurations.
Shared across training and validation scripts.
"""

import os
import yaml
import jsonschema
from pathlib import Path
from typing import Dict, Any, List
from itertools import product

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load and validate configuration from YAML file against its schema.
    
    Args:
        config_path: Path to the YAML config file.
    
    Returns:
        Validated configuration dictionary.
    
    Raises:
        FileNotFoundError: If config file or schema file doesn't exist.
        jsonschema.ValidationError: If config doesn't match schema.
        yaml.YAMLError: If YAML file is invalid.
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Load config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Find and load schema file
    # Try: {stem}.schema.yaml first (e.g., config.yaml -> config.schema.yaml)
    schema_file = config_file.parent / f"{config_file.stem}.schema.yaml"
    
    # If not found, try common schema names based on config file name
    if not schema_file.exists():
        if config_file.name == "config.yaml":
            schema_file = config_file.parent / "config.schema.yaml"
        elif "program" in config_file.name:
            schema_file = config_file.parent / "program.schema.yaml"
        else:
            # Try removing .config from name (e.g., program.config.yaml -> program.schema.yaml)
            name_without_config = config_file.stem.replace(".config", "")
            schema_file = config_file.parent / f"{name_without_config}.schema.yaml"
    
    if not schema_file.exists():
        # Warn and return config without validation if schema is missing
        # print(f"Warning: Schema file not found for {config_path}. Skipping validation.")
        return config
    
    with open(schema_file, 'r') as f:
        schema = yaml.safe_load(f)
    
    # Validate config against schema
    try:
        jsonschema.validate(instance=config, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Config validation failed: {e.message}") from e
    
    return config

def generate_experiment_name(experiment_config: Dict[str, Any], index: int) -> str:
    """Generate a name for an experiment based on its configuration."""
    parts = []
    
    # Include key parameters in the name (access nested structure)
    model_config = experiment_config.get('model_config', {})
    module_config = experiment_config.get('module_config', {})
    
    if 'model' in model_config:
        model_name = model_config['model'].replace('/', '-').replace('_', '-')
        parts.append(f"model-{model_name}")
    
    if 'strategy' in module_config:
        parts.append(f"strategy-{module_config['strategy']}")
    
    # If no parts, use index
    if not parts:
        return f"experiment-{index:04d}"
    
    return "_".join(parts)

def generate_sweep_experiments(sweeps: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """Generate all combinations from parameter sweeps (grid search)."""
    if not sweeps:
        return []
    
    # Get all parameter names and their values
    param_names = list(sweeps.keys())
    param_values = [sweeps[name] for name in param_names]
    
    # Generate Cartesian product
    experiments = []
    for combination in product(*param_values):
        experiment = dict(zip(param_names, combination))
        experiments.append(experiment)
    
    return experiments

def merge_configs(common: Dict[str, Any], experiment: Dict[str, Any]) -> Dict[str, Any]:
    """Merge common config with experiment-specific config (experiment overrides common)."""
    merged = common.copy()
    merged.update(experiment)
    return merged

def validate_experiment_config(config: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate that an experiment config has all required parameters."""
    errors = []
    
    model_config = config.get('model_config', {})
    module_config = config.get('module_config', {})
    
    if 'model' not in model_config:
        errors.append("Missing required parameter: model_config.model")
    if 'strategy' not in module_config:
        errors.append("Missing required parameter: module_config.strategy")
    
    return len(errors) == 0, errors

def expand_experiments(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expand the config into a list of individual experiment configurations.
    
    Returns:
        List of experiment configs, each merged with common parameters.
    """
    # Check if this is single-experiment mode
    if 'experiments' not in config:
        # Single experiment mode - return config as-is
        return [config]
    
    # Multi-experiment mode
    common = config.get('common', {})
    experiments_section = config.get('experiments', {})
    
    all_experiments = []
    
    # Generate sweep experiments
    sweeps = experiments_section.get('sweeps', {})
    sweep_experiments = generate_sweep_experiments(sweeps)
    
    for exp_config in sweep_experiments:
        merged = merge_configs(common, exp_config)
        all_experiments.append(merged)
    
    # Add explicit experiments
    explicit = experiments_section.get('explicit', [])
    if explicit is None:
        explicit = []
    for exp_config in explicit:
        # Extract name if provided
        exp_name = exp_config.pop('name', None)
        merged = merge_configs(common, exp_config)
        if exp_name:
            merged['_name'] = exp_name
        all_experiments.append(merged)
    
    return all_experiments

def print_experiment_summary(experiments: List[Dict[str, Any]]) -> bool:
    """
    Print a summary of the experiments and validate them.
    Returns True if all experiments are valid, False otherwise.
    """
    print(f"\nFound {len(experiments)} experiment(s):\n")
    
    all_valid = True
    for idx, exp_config in enumerate(experiments, 1):
        is_valid, errors = validate_experiment_config(exp_config)
        
        # Generate or use name
        exp_name = exp_config.get('_name')
        if not exp_name:
            exp_name = generate_experiment_name(exp_config, idx)
        
        print(f"Experiment {idx}: {exp_name}")
        print("-" * 80)
        
        if not is_valid:
            print("  ❌ VALIDATION ERRORS:")
            for error in errors:
                print(f"    - {error}")
            all_valid = False
        else:
            print("  ✅ Valid")
        
        # Show key parameters (from nested structure)
        print("  Parameters:")
        model_config = exp_config.get('model_config', {})
        module_config = exp_config.get('module_config', {})
        data_config = exp_config.get('data_config', {})
        
        if 'model' in model_config:
            print(f"    model: {model_config['model']}")
        if 'api_base' in model_config:
            print(f"    api_base: {model_config['api_base']}")
        if 'api_key_env' in model_config:
            print(f"    api_key_env: {model_config['api_key_env']}")
        if 'strategy' in module_config:
            print(f"    strategy: {module_config['strategy']}")
        if 'data_path' in data_config:
            print(f"    data_path: {data_config['data_path']}")
        
        # Show other parameters
        other_params = {k: v for k, v in exp_config.items() 
                       if k not in ['model_config', 'module_config', 'data_config', '_name']}
        if other_params:
            print("  Other parameters:")
            for key, value in other_params.items():
                print(f"    {key}: {value}")
        
        print()
        
    return all_valid

def flatten_config(config: Dict[str, Any], prefix: str = "", separator: str = "_") -> Dict[str, Any]:
    """
    Flatten a nested dictionary structure.
    
    Args:
        config: Nested dictionary to flatten
        prefix: Prefix to prepend to keys (for recursion)
        separator: Separator to use between nested keys
    
    Returns:
        Flattened dictionary with keys like 'lm_config_model', 'module_config_strategy'
    
    Example:
        {'lm_config': {'model': 'gpt-4', 'api_base': 'https://api.openai.com'}}
        -> {'lm_config_model': 'gpt-4', 'lm_config_api_base': 'https://api.openai.com'}
    """
    flattened = {}
    for key, value in config.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key
        
        if isinstance(value, dict):
            # Recursively flatten nested dictionaries
            flattened.update(flatten_config(value, new_key, separator))
        else:
            # Add the value with the flattened key
            flattened[new_key] = value
    
    return flattened

def inject_config_to_env(config: Dict[str, Any], prefix: str = "", overwrite: bool = True):
    """
    Flatten a YAML config dictionary and inject values into environment variables.
    
    Environment variable names are created by:
    1. Flattening nested keys with underscores (e.g., 'lm_config.model' -> 'lm_config_model')
    2. Converting to uppercase
    
    Args:
        config: Nested dictionary configuration
        prefix: Optional prefix to prepend to all environment variable names
        overwrite: If True, overwrite existing environment variables. If False, skip if already set.
                   Default is True to ensure config values take precedence.
    
    Example:
        config = {
            'lm_config': {
                'model': 'gpt-4',
                'api_base': 'https://api.openai.com',
                'api_key_env': 'OPENAI_API_KEY'
            }
        }
        inject_config_to_env(config)
        # Sets: LM_CONFIG_MODEL='gpt-4', LM_CONFIG_API_BASE='https://api.openai.com', etc.
    """
    flattened = flatten_config(config, prefix=prefix)
    
    for key, value in flattened.items():
        env_key = key.upper()
        
        # Skip if already set and overwrite is False
        if not overwrite and env_key in os.environ:
            continue
        
        # Convert value to string for environment variable
        os.environ[env_key] = str(value) if value is not None else ""
