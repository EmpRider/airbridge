"""
Gemini adapter - Implements browser automation for Google Gemini.
Migrated from the original undetected_mcp.py ask_gemini() logic.
"""
import time
import logging
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from mcp_manager.adapters.base_adapter import BaseAdapter
from mcp_manager.utils import human_type, random_delay, get_element_count, wait_for_response
from mcp_manager.browser import (
    get_browser_config, CHROME_PROFILE_DIR,
    USE_HUMAN_TYPING, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY,
    POLL_INTERVAL, get_temp_chat_preference
)

logger = logging.getLogger(__name__)


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini browser automation."""

    def process(self, prompt, model, chrome_path=None, headless=None):
        """Send prompt to Gemini and return the response.
        
        Args:
            prompt: The text prompt to send
            model: The chat model to use ('Fast', 'Thinking', or 'Pro')
            chrome_path: Optional path to Chrome executable
            headless: Optional headless mode setting
        """
        driver = None
        try:
            logger.info(f"=== NEW {self.adapter_name.upper()} REQUEST ===")
            logger.info(f"Prompt length: {len(prompt)} characters")

            try:
                # Get browser config and ensure headless setting is applied
                config = get_browser_config(chrome_path, headless, None)
                logger.info(f"Browser config: headless={config.headless}, chrome={config.chrome_executable}")
            except FileNotFoundError as e:
                logger.error(f"Chrome validation failed: {e}")
                return f"ERROR: {e}"

            try:
                driver = config.get_driver()
            except RuntimeError as e:
                logger.error(f"Driver creation failed: {e}")
                return f"ERROR: {e}"

            # Navigate to the URL from config
            target_url = self.url
            logger.info(f"Navigating to {target_url}")
            driver.get(target_url)
            time.sleep(5)

            # Check login requirement
            current_url = driver.current_url
            sign_in_selectors = self.get_all_selectors("sign-in")
            needs_login = "accounts.google.com" in current_url

            if not needs_login:
                for sel in sign_in_selectors:
                    if driver.find_elements(By.CSS_SELECTOR, sel):
                        needs_login = True
                        break

            if needs_login:
                logger.info("Login required. Switching to visible browser...")
                driver.quit()
                logger.info("Waiting 5s for Chrome to release profile lock...")
                time.sleep(5)

                original_headless = config.headless
                config.headless = False
                driver = config.get_driver()

                logger.info("Navigating to accounts.google.com for manual login")
                driver.get("https://accounts.google.com")

                logger.info("Waiting up to 5 minutes for user login...")
                start_wait = time.time()
                logged_in = False
                while time.time() - start_wait < 300:
                    title = driver.title.strip()
                    if title in ["Google Account", "Google Accounts"]:
                        logged_in = True
                        break
                    time.sleep(1)

                if not logged_in:
                    config.headless = original_headless
                    return "ERROR: Login timed out after 5 minutes."

                logger.info("Login successful! Navigating back...")
                driver.get(target_url)
                time.sleep(5)
                config.headless = original_headless

            # Start Temporary Chat if available and enabled
            use_temp_chat = get_temp_chat_preference()
            logger.info(f"Temp chat preference: {use_temp_chat}")

            if use_temp_chat:
                logger.debug("Attempting to start Temporary Chat...")
                temp_chat_selectors = self.get_all_selectors("temp-chat")
                for sel in temp_chat_selectors:
                    try:
                        temp_btns = driver.find_elements(By.CSS_SELECTOR, sel)
                        if temp_btns and temp_btns[0].is_displayed():
                            logger.info(f"Activating Temporary Chat via: {sel}")
                            temp_btns[0].click()
                            time.sleep(2)  # Wait for temp chat to activate
                            break
                    except Exception as e:
                        logger.debug(f"Temp-chat selector {sel} failed: {e}")
            else:
                logger.info("Temp chat disabled, using normal chat mode")

            # Select the specified model
            logger.info(f"Selecting model: {model}")
            self._select_mode(driver, model)

            # Wait for input field using optimized combined selectors
            logger.debug("Waiting for input field...")
            message_box_selectors = self.get_all_selectors("message-box")
            input_field = None
            if message_box_selectors:
                try:
                    # Combine all selectors with commas to find ANY of them in a single wait
                    combined_selector = ", ".join(message_box_selectors)
                    input_field = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, combined_selector))
                    )
                    logger.debug(f"Found input field using combined selector")
                except Exception as e:
                    logger.error(f"Failed to locate input field: {e}")

            if not input_field:
                return "ERROR: Failed to locate input field. Check selectors in config.json."

            random_delay(10, 50)
            prompt = prompt.replace('\n', ' ').replace('\r', '')

            # Capture initial completion signal count BEFORE sending
            complete_selectors = self.get_all_selectors("response-complete")
            container_selectors = self.get_all_selectors("response-container")
            initial_count = get_element_count(driver, complete_selectors)
            logger.info(f"Initial completion element count: {initial_count}")

            # Type prompt
            if USE_HUMAN_TYPING:
                human_type(input_field, prompt, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY)
            else:
                for char in prompt:
                    input_field.send_keys(char)
                    time.sleep(0.01)

            random_delay(10, 50)
            input_field.send_keys(Keys.RETURN)

            # Wait for response using completion signal
            response = wait_for_response(
                driver,
                complete_selectors=complete_selectors,
                container_selectors=container_selectors,
                initial_count=initial_count,
                poll_interval=POLL_INTERVAL,
            )

            logger.info(f"Response received: {len(response)} characters")
            return response

        except Exception as e:
            logger.error(f"Adapter FAILED: {e}", exc_info=True)
            if driver:
                try:
                    screenshot_path = CHROME_PROFILE_DIR.parent / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
                    driver.save_screenshot(str(screenshot_path))
                    logger.error(f"Screenshot saved to {screenshot_path}")
                except Exception:
                    pass
            return f"ERROR: {str(e)}"

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error closing driver: {e}")
            logger.info("=== REQUEST COMPLETE ===")

    def _select_mode(self, driver, model_name):
        """Select the specified chat model via the mode picker.
        
        Args:
            driver: Selenium WebDriver instance
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
                picker_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, combined_picker))
                )
                picker_btn.click()
                logger.debug("Mode picker clicked successfully")
                time.sleep(1)  # Wait for menu animation
            except Exception as e:
                logger.warning(f"Could not click mode picker: {e}. Mode may already be selected.")
                return
            
            # Find and click the specified model item
            combined_items = ", ".join(item_selectors)
            try:
                items = driver.find_elements(By.CSS_SELECTOR, combined_items)
                logger.debug(f"Found {len(items)} mode items")
                
                for item in items:
                    item_text = item.text.strip()
                    logger.debug(f"Checking item: '{item_text}'")
                    if model_name in item_text:
                        logger.info(f"Found and clicking '{model_name}' mode: {item_text}")
                        item.click()
                        time.sleep(2)  # Wait for selection to apply
                        return
                
                logger.warning(f"Could not find a mode item containing '{model_name}'")
            except Exception as e:
                logger.error(f"Error finding/clicking mode item: {e}")
                
        except Exception as e:
            logger.error(f"Failed to select mode '{model_name}': {e}", exc_info=True)
