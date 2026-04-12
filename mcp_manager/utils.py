"""
Shared utilities for Playwright-based LLM adapters.
Reusable across all adapters (Gemini, Claude, etc.)
"""
import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def human_type(locator, text, min_delay=0.0001, max_delay=0.0005, typo_prob=0.0001):
    """Type text with human-like delays and occasional typos."""
    for i, char in enumerate(text):
        delay = random.uniform(min_delay, max_delay)
        if random.random() < typo_prob and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await locator.type(wrong_char)
            await asyncio.sleep(random.uniform(0.01, 0.05))
            await locator.press('Backspace')
            await asyncio.sleep(random.uniform(0.005, 0.01))
        await locator.type(char)
        await asyncio.sleep(delay)


async def random_delay(min_ms=1, max_ms=5):
    """Add a random delay to simulate human behavior."""
    # uniform is more efficient than randint with division
    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)


async def fast_input(page, input_field, text):
    """Insert text instantly via keyboard API — no per-character delay."""
    await input_field.click()
    await page.keyboard.insert_text(text)


async def get_element_count(page, selectors):
    """
    Count DOM elements matching the first successful selector.

    Args:
        page: Playwright Page instance
        selectors: List of CSS selectors to try in order

    Returns:
        int: Number of matching elements found
    """
    if not selectors:
        return 0

    js_script = f"""
        () => {{
            var selectors = [{', '.join(f'"{s}"' for s in selectors)}];
            for (var i = 0; i < selectors.length; i++) {{
                var els = document.querySelectorAll(selectors[i]);
                if (els.length > 0) {{
                    return els.length;
                }}
            }}
            return 0;
        }}
    """
    try:
        return await page.evaluate(js_script)
    except Exception as e:
        logger.error(f"Error counting elements: {e}")
        return 0


async def wait_for_response(page, complete_selectors, container_selectors, initial_count, poll_interval=0.1,
                            max_iterations=3600):
    """
    Wait for LLM response completion.

    Stage 1: Use Playwright's native `wait_for_function` to wait until the count
             of 'complete_selectors' exceeds initial_count, executing the check
             in the browser for maximum efficiency.
    Stage 2: Extract the text from the last 'container_selectors' element.

    Args:
        page: Playwright Page instance
        complete_selectors: CSS selectors for the completion signal element
        container_selectors: CSS selectors for the response text container
        initial_count: Element count captured before the prompt was sent
        poll_interval: Seconds between polls (converted to ms for Playwright)
        max_iterations: Max polls before timeout (used to calculate timeout in ms)

    Returns:
        str: The response text from the new element
    """
    # Calculate timeout and polling in milliseconds
    timeout_ms = int(max_iterations * poll_interval * 1000)
    polling_ms = int(poll_interval * 1000)

    # JavaScript expression to run in the browser
    # Reuses the robust counting logic and then applies the baseline check.
    js_condition = f"""() => {{
        var selectors = [{', '.join(f'"{s}"' for s in complete_selectors)}];
        for (var i = 0; i < selectors.length; i++) {{
            var els = document.querySelectorAll(selectors[i]);
            if (els.length > 0) {{
                return els.length > {initial_count};
            }}
        }}
        return false;
    }}"""

    logger.info(f"Waiting for completion signal (initial count: {initial_count}, timeout: {timeout_ms}ms)...")

    try:
        # Wait for the condition to be true in the browser context
        await page.wait_for_function(js_condition, polling=polling_ms, timeout=timeout_ms)
        logger.info("Completion signal detected")
    except asyncio.TimeoutError:
        logger.warning(f"Response timeout after {timeout_ms}ms")
        return "TIMEOUT: Response took longer than expected"
    except Exception as e:
        logger.error(f"Error waiting for completion signal: {e}")
        return f"ERROR: {str(e)}"

    # Stage 2: Extract text from the last response container
    try:
        js_extract_script = f"""
            () => {{
                var selectors = [{', '.join(f'"{s}"' for s in container_selectors)}];
                for (var i = 0; i < selectors.length; i++) {{
                    var msgs = document.querySelectorAll(selectors[i]);
                    if (msgs.length > 0) {{
                        return msgs[msgs.length - 1].innerText;
                    }}
                }}
                return null;
            }}
        """
        response = await page.evaluate(js_extract_script)

        if response:
            logger.info(f"Response extracted: {len(response)} characters")
            return response
        else:
            return "ERROR: Completion signal detected but could not extract response text."

    except Exception as e:
        logger.error(f"Error extracting response: {e}")
        return f"ERROR: {str(e)}"
