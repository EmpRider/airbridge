"""
Adapter factory - Dynamically loads the correct adapter based on config.json task mapping.
"""
import json
import logging
from pathlib import Path

from mcp_manager.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

# Registry mapping adapter name -> adapter class
_ADAPTER_REGISTRY = {}

# Loaded config cache
_config_cache = None


def _get_config_path():
    """Resolve path to config.json relative to this package."""
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config(config_path=None):
    """Load and cache the adapter configuration."""
    global _config_cache
    if _config_cache is not None and config_path is None:
        return _config_cache

    path = Path(config_path) if config_path else _get_config_path()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        _config_cache = json.load(f)
    logger.info(f"Loaded config from {path}")
    return _config_cache


def register_adapter(name, adapter_class):
    """Register an adapter class by name."""
    if not issubclass(adapter_class, BaseAdapter):
        raise TypeError(f"{adapter_class} must be a subclass of BaseAdapter")
    _ADAPTER_REGISTRY[name] = adapter_class
    logger.debug(f"Registered adapter: {name} -> {adapter_class.__name__}")


def _auto_register():
    """Auto-register built-in adapters."""
    from mcp_manager.adapters.gemini.gemini_adapter import GeminiAdapter
    register_adapter("gemini", GeminiAdapter)


# Auto-register on import
_auto_register()


def get_available_tasks(config_path=None):
    """
    Return the list of available tasks from config.json.
    Each task includes its name, adapter, and description.
    """
    config = load_config(config_path)
    tasks = config.get("task", {})
    result = {}
    for task_name, task_config in tasks.items():
        result[task_name] = {
            "adapter": task_config.get("adapter", "unknown"),
            "description": task_config.get("description", "")
        }
    return result


def create_adapter(task_name, config_path=None):
    """
    Create an adapter instance for the given task name.

    Args:
        task_name: The task key from config.json (e.g. "thinking")
        config_path: Optional override path to config.json

    Returns:
        BaseAdapter: An instantiated adapter ready to process prompts
    """
    config = load_config(config_path)
    tasks = config.get("task", {})

    if task_name not in tasks:
        available = ", ".join(tasks.keys())
        raise ValueError(f"Unknown task '{task_name}'. Available tasks: {available}")

    task_config = tasks[task_name]
    adapter_name = task_config.get("adapter")

    if adapter_name not in _ADAPTER_REGISTRY:
        registered = ", ".join(_ADAPTER_REGISTRY.keys())
        raise ValueError(f"No adapter registered for '{adapter_name}'. Registered: {registered}")

    adapter_class = _ADAPTER_REGISTRY[adapter_name]
    adapter = adapter_class(task_name, task_config)
    logger.info(f"Created adapter: {adapter}")
    return adapter
