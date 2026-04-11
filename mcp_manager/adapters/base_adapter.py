"""
Base adapter - Abstract interface for all LLM browser automation adapters.
Every adapter (Gemini, Claude, etc.) must implement this contract.
"""
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class for LLM browser adapters."""

    def __init__(self, task_name, task_config):
        """
        Args:
            task_name: The task key from config.json (e.g. "thinking")
            task_config: The full task dict from config.json including adapter, description, selectors
        """
        self.task_name = task_name
        self.adapter_name = task_config.get("adapter", "unknown")
        self.description = task_config.get("description", "")
        self.url = task_config.get("url", "")
        self.selectors = task_config.get("selectors", {})

    @abstractmethod
    def process(self, prompt, model, chrome_path=None, headless=None, driver=None, tab_handle=None):
        """
        Execute the prompt against the target LLM via browser automation.

        Args:
            prompt: The text prompt to send
            model: The model variant to use (e.g., 'Fast', 'Thinking', 'Pro')
            chrome_path: Optional Chrome binary path override
            headless: Optional headless mode override
            driver: Optional pre-existing WebDriver instance (for pooling)
            tab_handle: Optional tab handle to use (for pooling)

        Returns:
            str: The LLM response text
        """
        pass

    def get_selector(self, key, fallback=None):
        """Get the first valid selector for a given key from the config."""
        selectors = self.selectors.get(key, [])
        if selectors:
            return selectors[0]
        return fallback

    def get_all_selectors(self, key):
        """Get all selectors for a given key to try in order."""
        return self.selectors.get(key, [])

    def __repr__(self):
        return f"<{self.__class__.__name__} task='{self.task_name}' adapter='{self.adapter_name}'>"
