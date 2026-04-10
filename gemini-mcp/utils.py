"""
Utility functions for Gemini MCP Server
"""
import time
import random
import logging
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


def human_type(element, text, min_delay=0.05, max_delay=0.15, typo_prob=0.05):
    """
    Type text with human-like delays and occasional typos
    
    Args:
        element: Selenium WebElement to type into
        text: Text to type
        min_delay: Minimum delay between keystrokes (seconds)
        max_delay: Maximum delay between keystrokes (seconds)
        typo_prob: Probability of making a typo (0.0 to 1.0)
    """
    for i, char in enumerate(text):
        # Random delay between keystrokes
        delay = random.uniform(min_delay, max_delay)
        
        # Occasional typo and correction
        if random.random() < typo_prob and i > 0:
            # Type wrong character
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            element.send_keys(wrong_char)
            time.sleep(random.uniform(0.1, 0.3))
            
            # Backspace to correct
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.05, 0.15))
            
            logger.debug(f"Simulated typo at position {i}")
        
        # Type the actual character
        element.send_keys(char)
        time.sleep(delay)


def wait_for_response(driver, poll_interval=1.0, stable_checks=3, min_length=20, max_iterations=3600):
    """
    Poll for Gemini response completion
    
    Args:
        driver: Selenium WebDriver instance
        poll_interval: Time between polls (seconds)
        stable_checks: Number of stable checks before considering complete
        min_length: Minimum response length to consider
        max_iterations: Maximum iterations (default 1 hour at 1 second intervals)
        
    Returns:
        str: Response text from Gemini
    """
    last_length = 0
    stable_count = 0
    iterations = 0
    
    logger.info("Polling for Gemini response...")
    
    while iterations < max_iterations:
        try:
            # Get all message elements
            messages = driver.execute_script("""
                const msgs = document.querySelectorAll('message-content');
                if (msgs.length > 0) {
                    return msgs[msgs.length - 1].innerText;
                }
                return null;
            """)
            
            if messages:
                current_length = len(messages)
                
                # Check if response has stopped growing
                if current_length > min_length:
                    if current_length == last_length:
                        stable_count += 1
                        if stable_count >= stable_checks:
                            logger.info(f"Response stable after {iterations} iterations")
                            return messages
                    else:
                        stable_count = 0
                        last_length = current_length
                        logger.debug(f"Response growing: {current_length} characters")
            
        except Exception as e:
            logger.error(f"Error polling response: {e}")
            return f"ERROR: {str(e)}"
        
        time.sleep(poll_interval)
        iterations += 1
    
    logger.warning(f"Response timeout after {max_iterations} iterations")
    return "TIMEOUT: Response took longer than expected"


def random_delay(min_ms=100, max_ms=500):
    """
    Add a random delay to simulate human behavior
    
    Args:
        min_ms: Minimum delay in milliseconds
        max_ms: Maximum delay in milliseconds
    """
    delay = random.randint(min_ms, max_ms) / 1000
    time.sleep(delay)
