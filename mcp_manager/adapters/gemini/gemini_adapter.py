"""
Gemini adapter - Playwright-based browser automation for Google Gemini.
Implements async execution with persistent session support for logins.
"""
import asyncio
import logging
from datetime import datetime

from mcp_manager.adapters.base_adapter import BaseAdapter
from mcp_manager.browser import CHROME_PROFILE_DIR
from mcp_manager.utils import human_type, random_delay, get_element_count, wait_for_response, fast_input

logger = logging.getLogger(__name__)

# Configuration constants
USE_HUMAN_TYPING = False
TYPING_DELAY_MIN = 0.00001
TYPING_DELAY_MAX = 0.00005
TYPO_PROBABILITY = 0.0002
POLL_INTERVAL = 0.1


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini browser automation using Playwright."""

    async def process(self, prompt, model, page=None, **kwargs):
        """Send prompt to Gemini and return the response.

        Args:
            prompt: The text prompt to send
            model: The chat model to use ('Fast', 'Thinking', or 'Pro')
            page: Playwright Page instance (from pool)
        """
        if page is None:
            return "ERROR: No page provided to adapter"

        try:
            logger.info(f"=== NEW {self.adapter_name.upper()} REQUEST ===")
            logger.info(f"Prompt length: {len(prompt)} characters")

            # Navigate to the URL from config with networkidle to minimize sleeps
            target_url = self.url
            logger.info(f"Navigating to {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Check login requirement — only triggers on positive sign-in evidence
            needs_login = await self._needs_login(page)

            if needs_login:
                logger.info("Login required, delegating to login handler...")
                
                from mcp_manager.login_handler import LoginHandler
                login_handler = LoginHandler()
                
                success = await login_handler.handle_login(
                    task_name=self.task_name,
                    target_context=page.context,
                    config=self.config
                )
                
                if not success:
                    return "ERROR: Login failed or timed out. Please try again."
                
                logger.info("Login successful, reloading page...")
                # Reload page to apply cookies
                await page.goto(target_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # Re-verify page state, waiting for the input field to be ready
                input_field = await self._wait_for_input(page)
                if not input_field:
                    raise RuntimeError("Input field not visible after login reload")
            else:
                # Wait for the input field to confirm the page is ready
                input_field = await self._wait_for_input(page)
                if not input_field:
                    raise RuntimeError("Input field not visible after navigation")

            # Select the specified model
            logger.info(f"Selecting model: {model}")
            await self._select_mode(page, model)

            # Wait for input field
            logger.debug("Waiting for input field...")
            message_box_selectors = self.get_all_selectors("message-box")
            input_field = None
            
            if message_box_selectors:
                try:
                    combined_selector = ", ".join(message_box_selectors)
                    input_field = page.locator(combined_selector).first
                    await input_field.wait_for(state="visible", timeout=30000)
                    logger.debug("Found input field")
                except Exception as e:
                    logger.error(f"Failed to locate input field: {e}")

            if not input_field:
                return "ERROR: Failed to locate input field. Check selectors in config.json."

            await random_delay(10, 50)
            prompt = prompt.replace('\n', ' ').replace('\r', '')

            # Capture initial completion signal count BEFORE sending
            complete_selectors = self.get_all_selectors("response-complete")
            container_selectors = self.get_all_selectors("response-container")
            initial_count = await get_element_count(page, complete_selectors)
            logger.info(f"Initial completion element count: {initial_count}")

            # Type prompt
            if USE_HUMAN_TYPING:
                await human_type(input_field, prompt, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY)
            else:
                await fast_input(page, input_field, prompt)

            await random_delay(10, 50)
            await input_field.press("Enter")

            # Wait for response using completion signal
            response = await wait_for_response(
                page,
                complete_selectors=complete_selectors,
                container_selectors=container_selectors,
                initial_count=initial_count,
                poll_interval=POLL_INTERVAL,
            )

            logger.info(f"Response received: {len(response)} characters")
            return response

        except Exception as e:
            logger.error(f"Adapter FAILED: {e}", exc_info=True)
            try:
                screenshot_path = CHROME_PROFILE_DIR.parent / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
                await page.screenshot(path=str(screenshot_path))
                logger.error(f"Screenshot saved to {screenshot_path}")
            except Exception:
                pass
            return f"ERROR: {str(e)}"

        finally:
            logger.info("=== REQUEST COMPLETE ===")

    # ------------------------------------------------------------------
    # Multi-turn chat session support
    # ------------------------------------------------------------------

    async def start_session(self, page, model):
        """Open Gemini, log in if needed, pick the model, and capture baseline.

        Called once per session. Subsequent turns run through send_in_session
        which never renavigates.
        """
        logger.info(f"=== START GEMINI SESSION model={model} ===")

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
            # networkidle to minimize explicit sleeps
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

        # Confirm the chat is ready and input field is visible. This is a crucial,
        # non-blocking alternative to explicit asyncio.sleep.
        input_field = await self._wait_for_input(page)
        if input_field is None:
            raise RuntimeError("Input field not visible after session setup")

        # Lock in the model for the life of the session
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
        """Send one turn inside a live Gemini session — no navigation.

        If `model` is provided and differs from the session's current model,
        re-open the mode picker and switch before typing. The model choice
        applies to this turn onward.
        """
        if page.is_closed():
            return "ERROR: page closed"

        # Auth-expiration check: Gemini bounces to accounts.google.com if
        # cookies died mid-session.
        current_url = page.url
        if "accounts.google.com" in current_url:
            return "LOGIN_EXPIRED: session lost authentication"

        # Per-turn model switch. We do this BEFORE waiting for the input
        # field because the mode picker is always rendered next to it.
        if model and model != state.get("model"):
            logger.info(
                f"Session mode switch: {state.get('model')} -> {model}"
            )
            await self._select_mode(page, model)
            state["model"] = model

        input_field = await self._wait_for_input(page)
        if input_field is None:
            return "LOGIN_EXPIRED: input field not present (likely signed out)"

        complete_selectors = self.get_all_selectors("response-complete")
        container_selectors = self.get_all_selectors("response-container")

        # Reconcile the running baseline with reality. If the user or some
        # other turn modified the DOM, trust the higher number.
        baseline = int(state.get("last_complete_count", 0) or 0)
        actual = await get_element_count(page, complete_selectors)
        baseline = max(baseline, actual)

        prompt = prompt.replace('\n', ' ').replace('\r', '')

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

        # Update running baseline so the next turn waits for count > new value
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
        """Wait for the Gemini input field to be visible. Returns locator or None."""
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
        """Select the specified chat model via the mode picker.
        
        Args:
            page: Playwright Page instance
            model_name: Name of the model to select ('Fast', 'Thinking', or 'Pro')
        """
        try:
            logger.info(f"Attempting to select '{model_name}' mode...")
            
            # Get selectors from config
            picker_selectors = self.get_all_selectors("mode-picker")
            item_selectors = self.get_all_selectors("mode-item")
            
            if not picker_selectors:
                logger.warning("No 'mode-picker' selectors found in config. Skipping mode selection.")
                return
            
            if not item_selectors:
                logger.warning("No 'mode-item' selectors found in config. Skipping mode selection.")
                return
            
            # Wait for and click the mode picker button
            combined_picker = ", ".join(picker_selectors)
            try:
                picker_btn = page.locator(combined_picker).first
                # Increased timeout to handle page load speed, and explicit visibility check
                await picker_btn.wait_for(state="visible", timeout=15000)
                await picker_btn.click()
                logger.debug("Mode picker clicked successfully")
                # Wait for menu animation — use wait_for_selector on a menu item
                combined_items = ", ".join(item_selectors)
                await page.locator(combined_items).first.wait_for(state="visible", timeout=10000)
            except Exception as e:
                logger.warning(f"Could not click mode picker or wait for menu: {e}. Mode may already be selected.")
                return
            
            # Find and click the specified model item
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
                        # Wait for selection menu to close and choice to apply
                        # A brief wait for the animation to complete and UI to update
                        await asyncio.sleep(1) 
                        return
                
                logger.warning(f"Could not find a mode item containing '{model_name}'")
            except Exception as e:
                logger.error(f"Error finding/clicking mode item: {e}")
                
        except Exception as e:
            logger.error(f"Failed to select mode '{model_name}': {e}", exc_info=True)
