"""
Adapter factory - Dynamically configures the generic adapter based on config.json task mapping.
Replaces the old registry-based pattern with a single GenericAdapter.
"""
import json
import logging
from pathlib import Path

from mcp_manager.adapters.generic_adapter import GenericAdapter

logger = logging.getLogger(__name__)

# Loaded config cache
_config_cache = None


def _get_config_path():
    """Resolve path to config.json at the project root."""
    return Path(__file__).resolve().parent.parent.parent / "config.json"


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
    Create a GenericAdapter instance for the given task name.

    Resolves the task's config reference, merges the config
    from the ``adapters`` section, and instantiates the generic adapter.

    Args:
        task_name: The task key from config.json (e.g. "thinking")
        config_path: Optional override path to config.json

    Returns:
        GenericAdapter: An instantiated generic adapter ready to process prompts
    """
    config = load_config(config_path)
    adapter_name, merged_config = _resolve_task(config, task_name)

    adapter = GenericAdapter(task_name, merged_config)
    logger.info(f"Created generic adapter for task: {task_name} (using config: {adapter_name})")
    return adapter
