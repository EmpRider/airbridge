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
from mcp_manager.utils import human_type, random_delay, wait_for_response
from mcp_manager.browser import (
    get_browser_config, CHROME_PROFILE_DIR,
    USE_HUMAN_TYPING, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY,
    POLL_INTERVAL, STABLE_CHECKS, MIN_RESPONSE_LENGTH
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

            # Wait for input field using selectors from config
            logger.debug("Waiting for input field...")
            message_box_selectors = self.get_all_selectors("message-box")
            input_field = None
            for sel in message_box_selectors:
                try:
                    input_field = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    if input_field:
                        logger.debug(f"Found input field with selector: {sel}")
                        break
                except Exception:
                    logger.debug(f"Selector '{sel}' not found, trying next...")
                    continue

            if not input_field:
                return "ERROR: Failed to locate input field. Check selectors in config.json."

            random_delay(500, 1000)
            prompt = prompt.replace('\n', ' ').replace('\r', '')

            # Type prompt
            if USE_HUMAN_TYPING:
                human_type(input_field, prompt, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY)
            else:
                for char in prompt:
                    input_field.send_keys(char)
                    time.sleep(0.01)

            random_delay(300, 700)
            input_field.send_keys(Keys.RETURN)

            # Wait for response using config selectors
            response_selectors = self.get_all_selectors("response-container")
            response = wait_for_response(
                driver,
                selectors=response_selectors,
                poll_interval=POLL_INTERVAL,
                stable_checks=STABLE_CHECKS,
                min_length=MIN_RESPONSE_LENGTH
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
