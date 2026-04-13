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
    from mcp_manager.adapters.chatgpt.chatgpt_adapter import ChatgptAdapter
    register_adapter("gemini", GeminiAdapter)
    register_adapter("chatgpt", ChatgptAdapter)


# Auto-register on import
_auto_register()


def _resolve_task(config, task_name):
    """Look up a task and merge its adapter config into a single dict.

    Returns (adapter_name, merged_config) where merged_config contains
    all adapter-level fields (url, selectors, login, models, ...) plus
    the task-level overrides (adapter, description).
    """
    tasks = config.get("tasks", {})
    if task_name not in tasks:
        available = ", ".join(tasks.keys())
        raise ValueError(f"Unknown task '{task_name}'. Available tasks: {available}")

    task_entry = tasks[task_name]
    adapter_name = task_entry.get("adapter")
    if not adapter_name:
        raise ValueError(f"Task '{task_name}' has no 'adapter' field")

    adapters = config.get("adapters", {})
    adapter_cfg = adapters.get(adapter_name)
    if adapter_cfg is None:
        available = ", ".join(adapters.keys())
        raise ValueError(
            f"Adapter '{adapter_name}' referenced by task '{task_name}' "
            f"not found in adapters config. Available: {available}"
        )

    # Merge: adapter config is the base, task-level fields override
    merged = {**adapter_cfg, **task_entry}
    return adapter_name, merged


def get_available_tasks(config_path=None):
    """Return available tasks in a structure ready for the MCP tool response.

    Shape::

        {
            "<task_name>": {
                "description": "...",
                "modes": [
                    {"name": "Fast", "description": "..."},
                    ...
                ]
            }
        }
    """
    config = load_config(config_path)
    tasks = config.get("tasks", {})
    adapters = config.get("adapters", {})
    result = {}
    for task_name, task_entry in tasks.items():
        adapter_name = task_entry.get("adapter", "unknown")
        adapter_cfg = adapters.get(adapter_name, {})
        modes = adapter_cfg.get("modes", [])
        result[task_name] = {
            "description": task_entry.get("description", ""),
            "modes": [
                {"name": m["name"], "description": m["description"]}
                for m in modes
            ],
        }
    return result


def create_adapter(task_name, config_path=None):
    """
    Create an adapter instance for the given task name.

    Resolves the task's adapter reference, merges the adapter config
    from the ``adapters`` section, and instantiates the adapter class.

    Args:
        task_name: The task key from config.json (e.g. "thinking")
        config_path: Optional override path to config.json

    Returns:
        BaseAdapter: An instantiated adapter ready to process prompts
    """
    config = load_config(config_path)
    adapter_name, merged_config = _resolve_task(config, task_name)

    if adapter_name not in _ADAPTER_REGISTRY:
        registered = ", ".join(_ADAPTER_REGISTRY.keys())
        raise ValueError(f"No adapter registered for '{adapter_name}'. Registered: {registered}")

    adapter_class = _ADAPTER_REGISTRY[adapter_name]
    adapter = adapter_class(task_name, merged_config)
    logger.info(f"Created adapter: {adapter}")
    return adapter
