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
        self.config = task_config  # Store full config for access to all fields
        self.adapter_name = task_config.get("adapter", "unknown")
        self.description = task_config.get("description", "")
        self.url = task_config.get("url", "")
        self.selectors = task_config.get("selectors", {})

    @abstractmethod
    async def process(self, prompt, model, page=None, **kwargs):
        """
        Execute the prompt against the target LLM via browser automation.

        Args:
            prompt: The text prompt to send
            model: The model variant to use (e.g., 'Fast', 'Thinking', 'Pro')
            page: Playwright Page instance (for pooling)
            **kwargs: Additional adapter-specific arguments

        Returns:
            str: The LLM response text
        """
        pass

    # ---- Multi-turn chat session support (optional for subclasses) ----

    async def start_session(self, page, model):
        """Bring a page to a state where send_in_session can be called repeatedly.

        Subclasses should: navigate to the chat URL, handle login once, select
        the model once, wait for the input field, and capture whatever baseline
        state (e.g. a response-element count) send_in_session needs.

        Args:
            page: Playwright Page instance pinned to this session
            model: Model variant to lock in for the session lifetime

        Returns:
            dict: Opaque per-session state. The SessionManager stores this and
                  passes it back into send_in_session unchanged. Adapters may
                  mutate it in place from send_in_session.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support chat sessions"
        )

    async def send_in_session(self, page, prompt, state, model=None):
        """Send one turn inside an already-initialized session page.

        Must NOT renavigate or re-login. MAY switch the chat mode if `model`
        is provided and differs from the session's current model — the
        adapter is responsible for updating `state["model"]` when it does.
        Must update `state` in place so the next turn has the correct
        baseline counts.

        Args:
            page: The session's pinned Playwright Page
            prompt: The user's next message
            state: The dict returned by start_session (mutated in place)
            model: Optional per-turn model override. If None, keep the
                   current session model. If set and different from
                   state["model"], the adapter switches the UI mode picker
                   before sending.

        Returns:
            str: Response text, or a sentinel starting with "LOGIN_EXPIRED"
                 if authentication was lost mid-session.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support chat sessions"
        )

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
