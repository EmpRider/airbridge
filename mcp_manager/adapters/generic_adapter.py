"""
Generic adapter - Playwright-based browser automation driven by config.json.
Replaces the old Adapter pattern.
"""
import asyncio
import logging
from mcp_manager.utils import human_type, random_delay, get_element_count, wait_for_response, fast_input

logger = logging.getLogger(__name__)

# Configuration constants
USE_HUMAN_TYPING = False
TYPING_DELAY_MIN = 0.00001
TYPING_DELAY_MAX = 0.00005
TYPO_PROBABILITY = 0.0002
POLL_INTERVAL = 0.1


class GenericAdapter:
    """Generic adapter for browser automation driven by config.json."""

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
        self.selectors = self._flatten_selectors(task_config.get("selectors", {}))

    @staticmethod
    def _flatten_selectors(selectors_config):
        """Flatten grouped selectors into a single lookup dict."""
        flat = {}
        for key, value in selectors_config.items():
            if isinstance(value, dict):
                # Grouped category — merge its children
                flat.update(value)
            else:
                # Legacy flat entry (value is a list of selector strings)
                flat[key] = value
        return flat

    async def enable_temp_chat(self, page):
        """Click the temp-chat toggle if the preference is enabled."""
        from mcp_manager.browser import get_temp_chat_preference
        if not get_temp_chat_preference():
            return
        selectors = self.get_all_selectors("temp-chat")
        if not selectors:
            logger.debug("No temp-chat selectors configured, skipping")
            return
        combined = ", ".join(selectors)
        try:
            btn = page.locator(combined).first
            await btn.wait_for(state="visible", timeout=5000)
            # Guard against double-toggle: check if already active
            is_pressed = await btn.get_attribute("aria-pressed")
            if is_pressed == "true":
                logger.debug("Temp chat already active, skipping click")
                return
            await btn.click()
            logger.info("Temp chat enabled")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Could not enable temp chat: {e}")

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

    async def start_session(self, page, model):
        """Open chat UI, log in if needed, pick the model, and capture baseline."""
        logger.info(f"=== START SESSION model={model} ===")

        target_url = self.url
        # networkidle to minimize explicit sleeps
        await page.goto(target_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await self._needs_login(page):
            logger.info("Login required at session start, delegating to login handler...")
            from mcp_manager.login_handler import LoginHandler
            login_handler = LoginHandler()
            success = await login_handler.handle_login(
                task_name=self.task_name,
                target_context=page.context,
                config=self.config,
            )
            if not success:
                raise RuntimeError("Login failed at session start")
            # Reload page to apply injected cookies
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

        input_field = await self._wait_for_input(page)
        if input_field is None:
            raise RuntimeError("Input field not visible after session setup")

        await self.enable_temp_chat(page)

        logger.info(f"Selecting model for session: {model}")
        await self._select_mode(page, model)

        complete_selectors = self.get_all_selectors("response-complete")
        initial_count = await get_element_count(page, complete_selectors)

        logger.info(f"Session baseline completion count: {initial_count}")
        return {
            "last_complete_count": initial_count,
            "model": model,
        }

    async def send_in_session(self, page, prompt, state, model=None):
        """Send one turn inside a live session \u2014 no navigation."""
        if page.is_closed():
            return "ERROR: page closed"

        # Auth-expiration check: bounce to login url logic if configured
        current_url = page.url
        login_url = self.config.get("login", {}).get("url", "")
        if login_url and login_url in current_url:
            return "LOGIN_EXPIRED: session lost authentication"

        # Per-turn model switch
        if model and model != state.get("model"):
            logger.info(f"Session mode switch: {state.get('model')} -> {model}")
            await self._select_mode(page, model)
            state["model"] = model

        input_field = await self._wait_for_input(page)
        if input_field is None:
            return "LOGIN_EXPIRED: input field not present (likely signed out)"

        complete_selectors = self.get_all_selectors("response-complete")
        container_selectors = self.get_all_selectors("response-container")

        baseline = int(state.get("last_complete_count", 0) or 0)
        actual = await get_element_count(page, complete_selectors)
        baseline = max(baseline, actual)

        await random_delay(10, 50)

        if USE_HUMAN_TYPING:
            await human_type(
                input_field, prompt,
                TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY,
            )
        else:
            await fast_input(page, input_field, prompt)

        await random_delay(10, 50)
        await input_field.press("Enter")

        response = await wait_for_response(
            page,
            complete_selectors=complete_selectors,
            container_selectors=container_selectors,
            initial_count=baseline,
            poll_interval=POLL_INTERVAL,
        )

        try:
            state["last_complete_count"] = await get_element_count(
                page, complete_selectors
            )
        except Exception as e:
            logger.warning(f"Could not update session baseline count: {e}")
            state["last_complete_count"] = baseline + 1

        logger.info(
            f"Session turn complete: {len(response)} chars, "
            f"new baseline={state['last_complete_count']}"
        )
        return response

    async def _needs_login(self, page) -> bool:
        """Check if the sign-in element from config exists on the page."""
        for sel in self.get_all_selectors("sign-in"):
            try:
                if await page.locator(sel).count() > 0:
                    logger.info(f"Login required: found sign-in element '{sel}'")
                    return True
            except Exception:
                pass
        return False

    async def _wait_for_input(self, page):
        """Wait for the input field to be visible."""
        selectors = self.get_all_selectors("message-box")
        if not selectors:
            return None
        try:
            field = page.locator(", ".join(selectors)).first
            await field.wait_for(state="visible", timeout=30000)
            return field
        except Exception as e:
            logger.error(f"Input field not visible: {e}")
            return None

    async def _select_mode(self, page, model_name):
        """Select the specified chat model via the mode picker."""
        if not model_name:
            return

        try:
            logger.info(f"Attempting to select '{model_name}' mode...")

            picker_selectors = self.get_all_selectors("mode-picker")
            item_selectors = self.get_all_selectors("mode-item")

            if not picker_selectors:
                logger.warning("No 'mode-picker' selectors found in config. Skipping mode selection.")
                return

            if not item_selectors:
                logger.warning("No 'mode-item' selectors found in config. Skipping mode selection.")
                return

            combined_picker = ", ".join(picker_selectors)
            try:
                picker_btn = page.locator(combined_picker).first
                await picker_btn.wait_for(state="visible", timeout=15000)
                await picker_btn.click()
                logger.debug("Mode picker clicked successfully")

                combined_items = ", ".join(item_selectors)
                await page.locator(combined_items).first.wait_for(state="visible", timeout=10000)
            except Exception as e:
                logger.warning(f"Could not click mode picker or wait for menu: {e}. Mode may already be selected.")
                return

            try:
                items = page.locator(combined_items)
                count = await items.count()
                logger.debug(f"Found {count} mode items")

                for i in range(count):
                    item = items.nth(i)
                    item_text = await item.inner_text()
                    item_text = item_text.strip()
                    logger.debug(f"Checking item: '{item_text}'")
                    if model_name in item_text:
                        logger.info(f"Found and clicking '{model_name}' mode: {item_text}")
                        await item.click()
                        await asyncio.sleep(1)
                        return

                logger.warning(f"Could not find a mode item containing '{model_name}'")
            except Exception as e:
                logger.error(f"Error finding/clicking mode item: {e}")

        except Exception as e:
            logger.error(f"Failed to select mode '{model_name}': {e}", exc_info=True)
