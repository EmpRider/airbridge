"""
Shared utilities for browser-based LLM adapters.
Reusable across all adapters (Gemini, Claude, etc.)
"""
import time
import random
import logging

from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


def human_type(element, text, min_delay=0.0001, max_delay=0.0005, typo_prob=0.0001):
    """Type text with human-like delays and occasional typos."""
    for i, char in enumerate(text):
        delay = random.uniform(min_delay, max_delay)
        if random.random() < typo_prob and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            element.send_keys(wrong_char)
            time.sleep(random.uniform(0.01, 0.05))
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.005, 0.01))
        element.send_keys(char)
        time.sleep(delay)


def random_delay(min_ms=1, max_ms=5):
    """Add a random delay to simulate human behavior."""
    delay = random.randint(min_ms, max_ms) / 1000
    time.sleep(delay)


def get_element_count(driver, selectors):
    """
    Count DOM elements matching the first successful selector.

    Args:
        driver: Selenium WebDriver instance
        selectors: List of CSS selectors to try in order

    Returns:
        int: Number of matching elements found
    """
    if not selectors:
        return 0

    js_script = f"""
        var selectors = [{', '.join(f'"{s}"' for s in selectors)}];
        for (var i = 0; i < selectors.length; i++) {{
            var els = document.querySelectorAll(selectors[i]);
            if (els.length > 0) {{
                return els.length;
            }}
        }}
        return 0;
    """
    try:
        return driver.execute_script(js_script)
    except Exception as e:
        logger.error(f"Error counting elements: {e}")
        return 0


def wait_for_response(driver, complete_selectors, container_selectors, initial_count, poll_interval=0.1, max_iterations=3600):
    """
    Wait for LLM response completion by monitoring element count changes.

    Stage 1: Poll until the count of 'complete_selectors' exceeds initial_count.
    Stage 2: Extract the text from the last 'container_selectors' element.

    Args:
        driver: Selenium WebDriver instance
        complete_selectors: CSS selectors for the completion signal element (e.g. message-actions)
        container_selectors: CSS selectors for the response text container (e.g. message-content)
        initial_count: Element count captured before the prompt was sent
        poll_interval: Seconds between polls
        max_iterations: Max polls before timeout

    Returns:
        str: The response text from the new element
    """
    iterations = 0
    logger.info(f"Waiting for completion signal (initial count: {initial_count})...")

    # Stage 1: Wait for completion signal count to increase
    while iterations < max_iterations:
        current_count = get_element_count(driver, complete_selectors)

        if current_count > initial_count:
            logger.info(f"Completion signal detected after {iterations} polls (count: {initial_count} -> {current_count})")
            break

        if iterations % 10 == 0 and iterations > 0:
            logger.debug(f"Still waiting... poll #{iterations}, count still {current_count}")

        time.sleep(poll_interval)
        iterations += 1
    else:
        logger.warning(f"Response timeout after {max_iterations} polls")
        return "TIMEOUT: Response took longer than expected"

    # Stage 2: Extract text from the last response container
    try:
        js_script = f"""
            var selectors = [{', '.join(f'"{s}"' for s in container_selectors)}];
            for (var i = 0; i < selectors.length; i++) {{
                var msgs = document.querySelectorAll(selectors[i]);
                if (msgs.length > 0) {{
                    return msgs[msgs.length - 1].innerText;
                }}
            }}
            return null;
        """
        response = driver.execute_script(js_script)

        if response:
            logger.info(f"Response extracted: {len(response)} characters")
            return response
        else:
            return "ERROR: Completion signal detected but could not extract response text."

    except Exception as e:
        logger.error(f"Error extracting response: {e}")
        return f"ERROR: {str(e)}"
