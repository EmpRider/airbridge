"""
Shared utilities for browser-based LLM adapters.
Reusable across all adapters (Gemini, Claude, etc.)
"""
import time
import random
import logging

from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


def human_type(element, text, min_delay=0.05, max_delay=0.15, typo_prob=0.05):
    """Type text with human-like delays and occasional typos."""
    for i, char in enumerate(text):
        delay = random.uniform(min_delay, max_delay)
        if random.random() < typo_prob and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            element.send_keys(wrong_char)
            time.sleep(random.uniform(0.1, 0.3))
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.05, 0.15))
        element.send_keys(char)
        time.sleep(delay)


def random_delay(min_ms=100, max_ms=500):
    """Add a random delay to simulate human behavior."""
    delay = random.randint(min_ms, max_ms) / 1000
    time.sleep(delay)


def wait_for_response(driver, selectors, poll_interval=1.0, stable_checks=3, min_length=20, max_iterations=3600):
    """Poll for LLM response completion using config-driven selectors."""
    last_length = 0
    stable_count = 0
    iterations = 0
    response_selectors = selectors if selectors else ["message-content"]

    logger.info("Polling for response...")

    while iterations < max_iterations:
        try:
            js_script = f"""
                var selectors = [{', '.join(f'"{s}"' for s in response_selectors)}];
                for (var i = 0; i < selectors.length; i++) {{
                    var msgs = document.querySelectorAll(selectors[i]);
                    if (msgs.length > 0) {{
                        return msgs[msgs.length - 1].innerText;
                    }}
                }}
                return null;
            """
            messages = driver.execute_script(js_script)

            if messages:
                current_length = len(messages)
                if current_length > min_length:
                    if current_length == last_length:
                        stable_count += 1
                        if stable_count >= stable_checks:
                            logger.info(f"Response stable after {iterations} iterations")
                            return messages
                    else:
                        stable_count = 0
                        last_length = current_length
                        logger.debug(f"Response growing: {current_length} chars")

        except Exception as e:
            logger.error(f"Error polling response: {e}")
            return f"ERROR: {str(e)}"

        time.sleep(poll_interval)
        iterations += 1

    logger.warning(f"Response timeout after {max_iterations} iterations")
    return "TIMEOUT: Response took longer than expected"
