"""
Gemini MCP Server using undetected-chromedriver
Clean, simple implementation that bypasses bot detection
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# Import configuration and utilities
from config import (
    GEMINI_URL, CHROME_PROFILE_DIR, LOG_FILE,
    USE_HEADLESS, WINDOW_SIZE,
    USE_HUMAN_TYPING, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY,
    SCRIPT_TIMEOUT, PAGE_LOAD_TIMEOUT, IMPLICIT_WAIT,
    POLL_INTERVAL, STABLE_CHECKS, MIN_RESPONSE_LENGTH,
    CHROME_BINARY_PATH
)
from utils import human_type, wait_for_response, random_delay

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),  # MCP safe
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)


def log_json(prefix, data):
    """Log JSON data with pretty formatting"""
    try:
        logger.debug(f"{prefix}: {json.dumps(data, indent=2)}")
    except:
        logger.debug(f"{prefix}: {data}")


# ---------------- BROWSER MANAGEMENT ----------------
def get_driver():
    """
    Create undetected Chrome driver
    Auto-patches ChromeDriver to bypass detection
    
    Returns:
        WebDriver instance
    """
    # Validate Chrome installation
    if not CHROME_BINARY_PATH:
        raise RuntimeError(
            "Chrome not found. Please install Google Chrome:\n"
            "https://www.google.com/chrome/\n"
            "Or set CHROME_PATH environment variable to Chrome executable path."
        )
    
    if not Path(CHROME_BINARY_PATH).exists():
        raise RuntimeError(
            f"Chrome not found at: {CHROME_BINARY_PATH}\n"
            "Please install Chrome or set CHROME_PATH environment variable."
        )
    
    logger.info(f"Launching undetected Chrome (headless={USE_HEADLESS})...")
    logger.info(f"Using Chrome at: {CHROME_BINARY_PATH}")
    
    # Configure Chrome options
    options = uc.ChromeOptions()
    
    # Explicitly set Chrome binary location
    options.binary_location = CHROME_BINARY_PATH
    
    # Set window size
    options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')
    
    # Headless mode (if enabled)
    if USE_HEADLESS:
        options.add_argument('--headless=new')
    
    # Create driver (auto-patches on first run)
    # Note: user_data_dir is passed directly to uc.Chrome, not via options
    driver = uc.Chrome(
        options=options,
        user_data_dir=str(CHROME_PROFILE_DIR),  # Pass as parameter, not argument
        version_main=None,  # Auto-detect Chrome version
        driver_executable_path=None,  # Auto-download if needed
        browser_executable_path=CHROME_BINARY_PATH  # Explicit Chrome path
    )
    
    # Set timeouts
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(IMPLICIT_WAIT)
    
    logger.info("Chrome launched successfully with undetected-chromedriver")
    return driver


# ---------------- GEMINI INTERACTION ----------------
def ask_gemini(prompt: str) -> str:
    """
    Send prompt to Gemini using undetected-chromedriver
    
    Args:
        prompt: Text prompt to send to Gemini
        
    Returns:
        str: Response from Gemini
    """
    driver = None
    
    try:
        logger.info("=== NEW GEMINI REQUEST ===")
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        # Launch browser
        driver = get_driver()
        
        # Navigate to Gemini
        logger.info(f"Navigating to {GEMINI_URL}")
        driver.get(GEMINI_URL)
        
        # Wait for page to load
        time.sleep(5)
        
        # Wait for input field
        logger.debug("Waiting for input field...")
        input_field = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-placeholder="Ask Gemini"]'))
        )
        
        # Add random delay
        random_delay(500, 1000)
        
        # Type prompt
        if USE_HUMAN_TYPING:
            logger.info("Using human-like typing")
            human_type(input_field, prompt, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY)
        else:
            logger.info("Using standard typing")
            for char in prompt:
                input_field.send_keys(char)
                time.sleep(0.05)
        
        # Add delay before submitting
        random_delay(300, 700)
        
        # Submit prompt
        logger.debug("Submitting prompt...")
        input_field.send_keys(Keys.RETURN)
        
        # Wait for response
        response = wait_for_response(
            driver,
            poll_interval=POLL_INTERVAL,
            stable_checks=STABLE_CHECKS,
            min_length=MIN_RESPONSE_LENGTH
        )
        
        logger.info(f"Response received: {len(response)} characters")
        return response
        
    except Exception as e:
        logger.error(f"ask_gemini FAILED: {e}", exc_info=True)
        
        # Try to capture screenshot
        if driver:
            try:
                screenshot_path = CHROME_PROFILE_DIR.parent / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
                driver.save_screenshot(str(screenshot_path))
                logger.error(f"Screenshot saved to {screenshot_path}")
            except:
                pass
        
        return f"ERROR: {str(e)}"
        
    finally:
        if driver:
            try:
                logger.debug("Closing browser...")
                driver.quit()
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
        
        logger.info("=== REQUEST COMPLETE ===")


# ---------------- MCP SERVER ----------------
async def mcp_server():
    """
    MCP (Model Context Protocol) server implementation
    Handles JSON-RPC communication via stdin/stdout
    """
    logger.info("MCP server started (undetected-chromedriver version)")
    
    while True:
        # Read from stdin
        line = await asyncio.to_thread(sys.stdin.readline)
        
        if not line:
            logger.info("STDIN closed. Shutting down.")
            break
        
        logger.debug(f"RAW INPUT: {line.strip()}")
        
        try:
            req = json.loads(line)
            log_json("REQUEST", req)
            
            req_id = req.get("id")
            method = req.get("method")
            
            response = {
                "jsonrpc": "2.0",
                "id": req_id
            }
            
            # ---------------- INITIALIZE ----------------
            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": "gemini-undetected-bridge",
                        "version": "1.0.0"
                    }
                }
            
            # ---------------- TOOLS ----------------
            elif method == "tools/list":
                response["result"] = {
                    "tools": [
                        {
                            "name": "ask_gemini",
                            "description": "Send a prompt to Gemini via undetected-chromedriver (bypasses bot detection)",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "Prompt to send to Gemini"
                                    }
                                },
                                "required": ["prompt"]
                            }
                        }
                    ]
                }
            
            # ---------------- RESOURCES (EMPTY) ----------------
            elif method == "resources/list":
                response["result"] = {"resources": []}
            
            elif method == "resources/templates/list":
                response["result"] = {"resourceTemplates": []}
            
            # ---------------- PROMPTS (EMPTY) ----------------
            elif method == "prompts/list":
                response["result"] = {"prompts": []}
            
            # ---------------- TOOL CALL ----------------
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                logger.debug(f"Tool call: {tool_name}")
                log_json("ARGS", arguments)
                
                if tool_name == "ask_gemini":
                    prompt = arguments.get("prompt", "")
                    # Run in thread to avoid blocking
                    output = await asyncio.to_thread(ask_gemini, prompt)
                    
                    response["result"] = {
                        "content": [
                            {
                                "type": "text",
                                "text": output
                            }
                        ]
                    }
                else:
                    response["error"] = {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
            
            # ---------------- NOTIFICATIONS ----------------
            elif req_id is None:
                continue
            
            # ---------------- UNKNOWN ----------------
            else:
                response["result"] = {}
            
            log_json("RESPONSE", response)
            
            # Write response to stdout
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            logger.error(f"MCP ERROR: {e}", exc_info=True)
            
            err = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


# ---------------- ENTRY POINT ----------------
if __name__ == "__main__":
    try:
        asyncio.run(mcp_server())
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}))
        sys.stdout.flush()
