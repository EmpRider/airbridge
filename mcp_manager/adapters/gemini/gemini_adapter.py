"""
Gemini adapter - Playwright-based browser automation for Google Gemini.
Implements async execution with persistent session support for logins.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from mcp_manager.adapters.base_adapter import BaseAdapter
from mcp_manager.utils import human_type, random_delay, get_element_count, wait_for_response
from mcp_manager.browser import get_browser_config, CHROME_PROFILE_DIR

logger = logging.getLogger(__name__)

# Configuration constants
USE_HUMAN_TYPING = True
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

            # Navigate to the URL from config
            target_url = self.url
            logger.info(f"Navigating to {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Check login requirement - improved detection
            current_url = page.url
            sign_in_selectors = self.get_all_selectors("sign-in")
            needs_login = "accounts.google.com" in current_url
            
            # Also check for sign-in buttons
            if not needs_login:
                for sel in sign_in_selectors:
                    try:
                        elements = await page.locator(sel).count()
                        if elements > 0:
                            needs_login = True
                            logger.info(f"Login required: found sign-in element with selector {sel}")
                            break
                    except Exception:
                        pass
            
            # Additional check: try to find the input field - if not found, likely needs login
            if not needs_login:
                message_box_selectors = self.get_all_selectors("message-box")
                if message_box_selectors:
                    try:
                        combined_selector = ", ".join(message_box_selectors)
                        input_count = await page.locator(combined_selector).count()
                        if input_count == 0:
                            needs_login = True
                            logger.info("Login required: message input field not found")
                    except Exception:
                        pass

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
                await input_field.type(prompt, delay=10)

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

    async def _handle_login(self, page, target_url):
        """
        Handle login requirement.
        For now, we'll return an error asking the user to log in manually.
        Future enhancement: implement persistent context switching.
        """
        logger.warning("Login required but automatic login not yet implemented in Playwright version")
        return "ERROR: Login required. Please run the server with --no-headless flag and log in manually first."

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
                await picker_btn.wait_for(state="visible", timeout=10000)
                await picker_btn.click()
                logger.debug("Mode picker clicked successfully")
                await asyncio.sleep(1)  # Wait for menu animation
            except Exception as e:
                logger.warning(f"Could not click mode picker: {e}. Mode may already be selected.")
                return
            
            # Find and click the specified model item
            combined_items = ", ".join(item_selectors)
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
                        await asyncio.sleep(2)  # Wait for selection to apply
                        return
                
                logger.warning(f"Could not find a mode item containing '{model_name}'")
            except Exception as e:
                logger.error(f"Error finding/clicking mode item: {e}")
                
        except Exception as e:
            logger.error(f"Failed to select mode '{model_name}': {e}", exc_info=True)
