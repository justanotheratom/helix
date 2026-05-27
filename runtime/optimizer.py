"""
Generic Optimizer Script for DSPy

This script provides a unified interface to apply any DSPy optimizer to a module,
given the optimizer type and its configuration parameters.
"""

import importlib
import json
import dspy
from dspy.primitives import Example, Module
from dspy.teleprompt import Teleprompter
from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path

# Mapping of optimizer names to their module paths
OPTIMIZER_REGISTRY = {
    "BootstrapFewShot": "dspy.teleprompt.bootstrap",
    "BootstrapFewShotWithRandomSearch": "dspy.teleprompt.random_search",
    "BootstrapFewShotWithOptuna": "dspy.teleprompt.teleprompt_optuna",
    "COPRO": "dspy.teleprompt.copro_optimizer",
    "MIPROv2": "dspy.teleprompt.mipro_optimizer_v2",
    "SIMBA": "dspy.teleprompt.simba",
    "GEPA": "dspy.teleprompt.gepa.gepa",
    "BootstrapFinetune": "dspy.teleprompt.bootstrap_finetune",
    "GRPO": "dspy.teleprompt.grpo",
    "Ensemble": "dspy.teleprompt.ensemble",
    "LabeledFewShot": "dspy.teleprompt.vanilla",
    "KNNFewShot": "dspy.teleprompt.knn_fewshot",
    "AvatarOptimizer": "dspy.teleprompt.avatar_optimizer",
    "BetterTogether": "dspy.teleprompt.bettertogether",
    "InferRules": "dspy.teleprompt.infer_rules",
    "SequentialFeedbackOptimizer": "sequential_feedback_optimizer",
}


class OptimizerConfig:
    """Configuration for optimizer initialization and compilation."""
    
    def __init__(
        self,
        optimizer: str,
        optimizer_params: Optional[Dict[str, Any]] = None,
        compile_params: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize optimizer configuration.
        
        Args:
            optimizer: Name of the optimizer class (e.g., "BootstrapFewShot")
            optimizer_params: Parameters to pass to optimizer __init__
            compile_params: Parameters to pass to optimizer.compile()
        """
        self.optimizer = optimizer
        self.optimizer_params = optimizer_params or {}
        self.compile_params = compile_params or {}


def create_lm_from_config(lm_config: Union[str, Dict[str, Any]], config_base_dir: Path = None) -> dspy.LM:
    """
    Create a dspy.LM instance from a config dict or string reference.

    Args:
        lm_config: Dict with model, api_base, api_key_env (or api_key), or a string reference
                  (string references should be resolved before calling this function)
        config_base_dir: Base directory for resolving relative paths (e.g., service credentials)

    Returns:
        A dspy.LM instance
    """
    import os

    if isinstance(lm_config, str):
        raise ValueError(
            f"lm_config is a string reference '{lm_config}' but should have been resolved to a dict. "
            "This indicates a bug in the resolution logic."
        )

    model = lm_config.get("model")
    api_base = lm_config.get("api_base")
    api_key = lm_config.get("api_key")
    base_model = lm_config.get("base_model")

    # Handle Vertex AI configuration
    if lm_config.get("vertex_project_env") or lm_config.get("vertex_location_env"):
        project_env = lm_config.get("vertex_project_env", "VERTEXAI_PROJECT")
        location_env = lm_config.get("vertex_location_env", "VERTEXAI_LOCATION")

        project = os.getenv(project_env)
        location = os.getenv(location_env)

        if not project:
            raise ValueError(f"Vertex AI project env var '{project_env}' not set")
        if not location:
            raise ValueError(f"Vertex AI location env var '{location_env}' not set")

        # Set environment variables for Vertex AI
        os.environ["VERTEXAI_PROJECT"] = project
        os.environ["VERTEXAI_LOCATION"] = location

        # Handle service credentials
        service_credentials_path = lm_config.get("service_credentials")
        if service_credentials_path:
            if config_base_dir and not Path(service_credentials_path).is_absolute():
                service_credentials_path = config_base_dir / service_credentials_path

            with open(service_credentials_path, 'r') as f:
                vertex_credentials = json.load(f)

            vertex_credentials_json = json.dumps(vertex_credentials)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(service_credentials_path)

        # Create Vertex AI LM
        _consumed = {"model", "api_base", "api_key", "api_key_env", "base_model",
                     "vertex_project_env", "vertex_location_env", "service_credentials"}
        extra_kwargs = {k: v for k, v in lm_config.items() if k not in _consumed}
        if base_model:
            return dspy.LM(model=model, base_model=base_model, **extra_kwargs)
        else:
            return dspy.LM(model=model, **extra_kwargs)

    # Standard API key based configuration
    if not api_key and "api_key_env" in lm_config:
        api_key = os.getenv(lm_config["api_key_env"])
        if not api_key:
            raise ValueError(f"API key env var '{lm_config['api_key_env']}' not set")

    # Forward additional dspy.LM/litellm kwargs (timeout, num_retries, cache,
    # temperature, max_tokens, stream, ...). Without this, fields like
    # `timeout: 300` in YAML are silently dropped and a stalled streaming
    # response can block the whole pipeline indefinitely (no socket timeout).
    _consumed = {"model", "api_base", "api_key", "api_key_env", "base_model",
                 "vertex_project_env", "vertex_location_env", "service_credentials"}
    extra_kwargs = {k: v for k, v in lm_config.items() if k not in _consumed}
    return dspy.LM(model, api_base=api_base, api_key=api_key, **extra_kwargs)


def get_optimizer_class(optimizer_name: Optional[str]) -> Optional[type[Teleprompter]]:
    """
    Dynamically import and return the optimizer class.
    
    Args:
        optimizer_name: Name of the optimizer class, or None for baseline runs
        
    Returns:
        The optimizer class, or None if optimizer_name is None
    """
    if optimizer_name is None:
        return None
    
    if optimizer_name not in OPTIMIZER_REGISTRY:
        available = ", ".join(OPTIMIZER_REGISTRY.keys())
        raise ValueError(
            f"Unknown optimizer: {optimizer_name}. "
            f"Available optimizers: {available}, or None for baseline runs"
        )
    
    module_path = OPTIMIZER_REGISTRY[optimizer_name]
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        # Fallback for some optimizers that might be in different paths in different dspy versions
        if optimizer_name == "BootstrapFewShot":
             module = importlib.import_module("dspy.teleprompt")
        else:
             raise

    # Handle special case for GEPA
    if optimizer_name == "GEPA":
        return module.GEPA
    
    # Handle special case for LabeledFewShot
    if optimizer_name == "LabeledFewShot":
        return module.LabeledFewShot
    
    # Most optimizers use the same name as the class
    if hasattr(module, optimizer_name):
        return getattr(module, optimizer_name)
    
    raise ValueError(f"Optimizer class {optimizer_name} not found in module {module_path}")


def optimize_program(
    student: Module,
    config: Union[OptimizerConfig, Dict[str, Any]],
    **override_params
) -> Module:
    """
    Apply an optimizer to a DSPy program using a configuration.
    
    Args:
        student: The DSPy module/program to optimize
        config: Configuration dict or OptimizerConfig object with:
            - optimizer: Name of the optimizer class, or None/null for baseline run
            - optimizer_params: Dict of parameters for optimizer initialization
            - compile_params: Dict of parameters for optimizer.compile()
        **override_params: Additional parameters to override in compile_params
        
    Returns:
        The compiled program, or the student unchanged if optimizer is None (baseline run)
    """
    # Convert dict config to OptimizerConfig if needed
    if isinstance(config, dict):
        config = OptimizerConfig(**config)
    
    # Handle baseline run (no optimizer)
    if config.optimizer is None:
        # Return student unchanged for baseline run
        return student
    
    # Merge override params into compile_params
    compile_params = {**config.compile_params, **override_params}
    
    # Get optimizer class
    optimizer_class = get_optimizer_class(config.optimizer)
    
    # Handle special cases
    if config.optimizer == "Ensemble":
        # Ensemble takes a list of programs, not student/trainset
        if "programs" not in compile_params:
            raise ValueError(
                "Ensemble optimizer requires 'programs' in compile_params, "
                "not 'trainset'"
            )
        optimizer = optimizer_class(**config.optimizer_params)
        return optimizer.compile(compile_params["programs"])
    
    if config.optimizer == "KNNFewShot":
        # KNNFewShot requires trainset in __init__, not compile
        if "trainset" not in config.optimizer_params:
            if "trainset" in compile_params:
                config.optimizer_params["trainset"] = compile_params.pop("trainset")
            else:
                raise ValueError(
                    "KNNFewShot requires 'trainset' in optimizer_params or compile_params"
                )
        optimizer = optimizer_class(**config.optimizer_params)
        return optimizer.compile(student, **compile_params)
    
    # Process optimizer_params to handle special cases like teacher_settings, prompt_model_config
    optimizer_params = dict(config.optimizer_params)
    
    # Handle teacher_settings with lm_config - create actual LM instance
    if "teacher_settings" in optimizer_params:
        teacher_settings = optimizer_params["teacher_settings"]
        if "lm_config" in teacher_settings:
            teacher_lm = create_lm_from_config(teacher_settings["lm_config"])
            teacher_settings = {**teacher_settings, "lm": teacher_lm}
            del teacher_settings["lm_config"]
            optimizer_params["teacher_settings"] = teacher_settings
    
    # Handle prompt_model_config - create LM for MIPROv2
    if "prompt_model_config" in optimizer_params:
        optimizer_params["prompt_model"] = create_lm_from_config(optimizer_params.pop("prompt_model_config"))
    
    # Handle task_model_config - create LM for MIPROv2
    if "task_model_config" in optimizer_params:
        optimizer_params["task_model"] = create_lm_from_config(optimizer_params.pop("task_model_config"))
    
    # Handle reflection LM config for optimizers that need it
    if config.optimizer in {"GEPA", "SequentialFeedbackOptimizer"}:
        if "reflection_lm_config" in optimizer_params:
            reflection_lm = create_lm_from_config(optimizer_params.pop("reflection_lm_config"))
            optimizer_params["reflection_lm"] = reflection_lm

    # Handle GEPA-specific parameters
    if config.optimizer == "GEPA":
        if "instruction_proposer_config" in optimizer_params:
            proposer_config = optimizer_params.pop("instruction_proposer_config")
            if proposer_config == "multimodal":
                from dspy.teleprompt.gepa.instruction_proposal import MultiModalInstructionProposer
                optimizer_params["instruction_proposer"] = MultiModalInstructionProposer()
            elif proposer_config == "generalizing":
                from instruction_proposer import GeneralizingInstructionProposer

                prompt_template = optimizer_params.pop("instruction_proposer_prompt_template", None)
                optimizer_params["instruction_proposer"] = GeneralizingInstructionProposer(
                    prompt_template=prompt_template,
                    log_dir=optimizer_params.get("log_dir"),
                )
            else:
                raise ValueError(
                    f"Unknown instruction_proposer_config: {proposer_config}. "
                    "Supported: multimodal, generalizing"
                )

        # Handle component_selector_config — translate config-side shorthand
        # into a callable component_selector. Supports:
        #   { fixed: [<predictor_name>, ...] }     → optimize only those predictors
        #   { route_aware: <route_name> }          → enable component-aware
        #     batch sampling: each iteration's minibatch contains only rows
        #     that route to the predictor RoundRobin is about to target,
        #     keeping the reflective dataset at full size for both predictors.
        #     See component_aware_sampler.py.
        if "component_selector_config" in optimizer_params:
            sel_config = optimizer_params.pop("component_selector_config")
            if isinstance(sel_config, dict) and "fixed" in sel_config:
                fixed_components = list(sel_config["fixed"])

                def _fixed_selector(state, trajectories, subsample_scores,
                                    candidate_idx, candidate, _fc=fixed_components):
                    return list(_fc)

                optimizer_params["component_selector"] = _fixed_selector
            elif isinstance(sel_config, dict) and "route_aware" in sel_config:
                from component_aware_sampler import build_route_aware_components

                route_name = sel_config["route_aware"]
                # Use existing reflection_minibatch_size as the sampler's
                # batch size, then NULL it out (gepa.api.py asserts None when
                # a custom batch_sampler is provided).
                mb_size = optimizer_params.get("reflection_minibatch_size", 15)
                seed = optimizer_params.get("seed", 0) or 0
                selector, sampler = build_route_aware_components(
                    route_name=route_name, minibatch_size=mb_size, seed=seed,
                )
                # Override candidate_selection_strategy with our capturing
                # wrapper (Literal annotation isn't enforced at runtime; gepa
                # accepts a CandidateSelector instance per gepa/api.py:300).
                optimizer_params["candidate_selection_strategy"] = selector
                optimizer_params["reflection_minibatch_size"] = None
                # Keep component_selector at default "round_robin" so the
                # per-candidate counter advances AFTER our sampler reads it.
                optimizer_params.setdefault("component_selector", "round_robin")
                # Pass the sampler through gepa_kwargs.
                gepa_kwargs = optimizer_params.get("gepa_kwargs") or {}
                gepa_kwargs["batch_sampler"] = sampler
                optimizer_params["gepa_kwargs"] = gepa_kwargs
            else:
                raise ValueError(
                    f"Unknown component_selector_config: {sel_config!r}. "
                    "Supported: { fixed: [<predictor_name>, ...] }, "
                    "{ route_aware: <route_name> }"
                )

        # Handle log_dir - if set to "__auto__", will be replaced by compile.py with actual results dir
        # This allows dynamic log directory based on the run
        if optimizer_params.get("log_dir") == "__auto__":
            # Will be set by compile.py before calling optimize_program
            pass
    
    # Standard case: initialize optimizer and compile
    optimizer = optimizer_class(**optimizer_params)
    
    # Ensure trainset is provided (required by most optimizers)
    if "trainset" not in compile_params:
        raise ValueError(
            f"{config.optimizer} requires 'trainset' in compile_params"
        )
    
    # Filter compile_params to only include supported arguments
    # Some optimizers (like BootstrapFewShot) don't accept valset
    optimizers_with_valset = {"MIPROv2", "MIPRO", "BayesianSignatureOptimizer", "BootstrapFewShotWithRandomSearch", "GEPA"}
    if config.optimizer not in optimizers_with_valset and "valset" in compile_params:
        compile_params = {k: v for k, v in compile_params.items() if k != "valset"}
    
    return optimizer.compile(student, **compile_params)


def load_schema(schema_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the YAML schema for optimizer configuration.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")
    
    if schema_path is None:
        # Default to schema in same directory as this file
        schema_path = Path(__file__).parent / "config.schema.yaml"
    
    with open(schema_path, "r") as f:
        return yaml.safe_load(f)


def validate_config(config: Dict[str, Any], schema_path: Optional[str] = None) -> None:
    """
    Validate a configuration dictionary against the optimizer-specific schema.
    """
    try:
        import jsonschema
    except ImportError:
        raise ImportError("jsonschema is required. Install with: pip install jsonschema")
    
    # Load full schema
    schema = load_schema(schema_path)
    
    # Validate against full schema
    jsonschema.validate(instance=config, schema=schema)
