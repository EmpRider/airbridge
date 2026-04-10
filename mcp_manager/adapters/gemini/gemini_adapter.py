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
    POLL_INTERVAL
)

logger = logging.getLogger(__name__)


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini browser automation."""

    def process(self, prompt, chrome_path=None, headless=None):
        """Send prompt to Gemini and return the response."""
        driver = None
        try:
            logger.info(f"=== NEW {self.adapter_name.upper()} REQUEST ===")
            logger.info(f"Prompt length: {len(prompt)} characters")

            try:
                config = get_browser_config(chrome_path, headless)
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

            # Start Temporary Chat if available
            logger.debug("Start Temporary Chat if available...")
            temp_chat_selectors = self.get_all_selectors("temp-chat")
            for sel in temp_chat_selectors:
                try:
                    temp_btns = driver.find_elements(By.CSS_SELECTOR, sel)
                    if temp_btns and temp_btns[0].is_displayed():
                        logger.info(f"Activating Temporary Chat via: {sel}")
                        temp_btns[0].click()
                        break
                except Exception as e:
                    logger.debug(f"Temp-chat selector {sel} failed: {e}")

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
