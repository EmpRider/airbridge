"""
Gemini MCP Server using undetected-chromedriver
Clean, simple implementation that bypasses bot detection
"""
import asyncio
import json
import logging
import sys
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================================
# DEPENDENCY VALIDATION
# ============================================================
def check_and_install_dependencies():
    """Check for required packages and suggest installation if missing"""
    missing_packages = []
    
    try:
        import undetected_chromedriver as uc
    except ImportError:
        missing_packages.append("undetected-chromedriver")
    
    try:
        from selenium.webdriver.common.by import By
    except ImportError:
        missing_packages.append("selenium")
    
    if missing_packages:
        error_msg = f"Missing required packages: {', '.join(missing_packages)}\n"
        error_msg += "Install them with:\n"
        error_msg += f"  pip install {' '.join(missing_packages)}\n"
        error_msg += "Or:\n"
        error_msg += f"  pip install -r requirements.txt\n"
        raise ImportError(error_msg)


# Validate dependencies before importing
try:
    check_and_install_dependencies()
except ImportError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

# Now safe to import
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# Import configuration and utilities
try:
    from config import (
        GEMINI_URL, CHROME_PROFILE_DIR, LOG_FILE,
        USE_HEADLESS, WINDOW_SIZE,
        USE_HUMAN_TYPING, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY,
        SCRIPT_TIMEOUT, PAGE_LOAD_TIMEOUT, IMPLICIT_WAIT,
        POLL_INTERVAL, STABLE_CHECKS, MIN_RESPONSE_LENGTH,
        CHROME_BINARY_PATH
    )
    from utils import human_type, wait_for_response, random_delay
except ImportError as e:
    print(f"ERROR: Failed to import config or utils: {e}", file=sys.stderr)
    print("Make sure config.py and utils.py exist in the same directory.", file=sys.stderr)
    sys.exit(1)

# ============================================================
# LOGGING SETUP
# ============================================================
def setup_logging(log_file: Path = None):
    """Setup logging with fallback to stderr if file fails"""
    if log_file is None:
        log_file = LOG_FILE
    
    handlers = [logging.StreamHandler(sys.stderr)]  # Always log to stderr for MCP
    
    # Try to add file handler
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: Could not create log file at {log_file}: {e}", file=sys.stderr)
    
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )
    return logging.getLogger(__name__)


logger = setup_logging()


def log_json(prefix, data):
    """Log JSON data with pretty formatting"""
    try:
        logger.debug(f"{prefix}: {json.dumps(data, indent=2)}")
    except:
        logger.debug(f"{prefix}: {data}")


# ============================================================
# CHROME DETECTION & VALIDATION
# ============================================================
def find_chrome_executable():
    """
    Comprehensive Chrome detection across multiple locations
    
    Returns:
        str: Path to Chrome executable, or None if not found
    """
    import platform
    import shutil
    
    system = platform.system()
    
    # Try common command names first
    for cmd in ["google-chrome", "chrome", "chromium", "chromium-browser"]:
        path = shutil.which(cmd)
        if path:
            logger.debug(f"Found Chrome via PATH: {path}")
            return path
    
    if system == "Windows":
        possible_paths = [
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            f"{Path.home()}/AppData/Local/Google/Chrome/Application/chrome.exe",
            "C:/Program Files/Chromium/Application/chrome.exe",
        ]
    elif system == "Darwin":  # macOS
        possible_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:  # Linux
        possible_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]
    
    for path_str in possible_paths:
        path = Path(path_str)
        if path.exists():
            logger.debug(f"Found Chrome at: {path}")
            return str(path)
    
    return None


def validate_chrome(chrome_path: str = None) -> str:
    """
    Validate Chrome installation and return path
    
    Args:
        chrome_path: Explicit Chrome path to validate, or None to auto-detect
        
    Returns:
        str: Valid Chrome executable path
        
    Raises:
        FileNotFoundError: If Chrome not found
    """
    # Use provided path if given
    if chrome_path:
        path = Path(chrome_path)
        if path.exists() and path.is_file():
            logger.info(f"✓ Chrome found at: {chrome_path}")
            return str(chrome_path)
        else:
            logger.error(f"✗ Chrome not found at specified path: {chrome_path}")
            raise FileNotFoundError(f"Chrome not found at: {chrome_path}")
    
    # Try from config
    if CHROME_BINARY_PATH:
        path = Path(CHROME_BINARY_PATH)
        if path.exists():
            logger.info(f"✓ Using Chrome from config: {CHROME_BINARY_PATH}")
            return CHROME_BINARY_PATH
    
    # Auto-detect
    logger.debug("Auto-detecting Chrome installation...")
    detected = find_chrome_executable()
    
    if detected:
        logger.info(f"✓ Chrome auto-detected at: {detected}")
        return detected
    
    # Not found - provide helpful error message
    error_msg = (
        "Chrome not found!\n\n"
        "Please install Google Chrome:\n"
        "  https://www.google.com/chrome/\n\n"
        "Or specify its path:\n"
        "  Option 1: Set CHROME_PATH environment variable\n"
        "  Option 2: Pass --chrome-path argument to this script\n"
        "  Option 3: Edit gemini-mcp/config.py and set CHROME_BINARY_PATH\n\n"
        "Common installation paths:\n"
        "  Windows: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\n"
        "  macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
        "  Linux: /usr/bin/google-chrome or /usr/bin/chromium"
    )
    raise FileNotFoundError(error_msg)


# ============================================================
# BROWSER MANAGEMENT
# ============================================================
class BrowserConfig:
    """Centralized browser configuration with CLI override support"""
    
    def __init__(self, chrome_path=None, headless=None, profile_dir=None):
        """
        Initialize browser configuration
        
        Args:
            chrome_path: Override Chrome path (from CLI or env)
            headless: Override headless mode
            profile_dir: Override profile directory
        """
        self.chrome_path = chrome_path or CHROME_BINARY_PATH
        self.headless = headless if headless is not None else USE_HEADLESS
        self.profile_dir = profile_dir or CHROME_PROFILE_DIR
        
        # Validate Chrome on initialization
        self.chrome_executable = validate_chrome(self.chrome_path)
        
        # Ensure profile directory exists
        self.profile_dir.mkdir(parents=True, exist_ok=True)
    
    def get_driver(self):
        """
        Create undetected Chrome driver with validated configuration
        
        Returns:
            WebDriver instance
            
        Raises:
            Exception: If driver creation fails
        """
        try:
            logger.info(f"Launching undetected Chrome (headless={self.headless})...")
            logger.debug(f"Using Chrome at: {self.chrome_executable}")
            logger.debug(f"Profile dir: {self.profile_dir}")
            
            # Configure Chrome options
            options = uc.ChromeOptions()
            
            # Explicitly set Chrome binary location
            options.binary_location = self.chrome_executable
            
            # Set window size
            options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')
            
            # Headless mode (if enabled)
            if self.headless:
                options.add_argument('--headless=new')
            
            # Add anti-detection arguments
            options.add_argument('--disable-blink-features=AutomationControlled')

            
            # Create driver (auto-patches on first run)
            driver = uc.Chrome(
                options=options,
                user_data_dir=str(self.profile_dir),
                version_main=None,  # Auto-detect Chrome version
                driver_executable_path=None,  # Auto-download if needed
                browser_executable_path=self.chrome_executable
            )
            
            # Set timeouts
            driver.set_script_timeout(SCRIPT_TIMEOUT)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(IMPLICIT_WAIT)
            
            logger.info("✓ Chrome launched successfully with undetected-chromedriver")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to create WebDriver: {e}", exc_info=True)
            raise RuntimeError(
                f"ChromeDriver creation failed: {e}\n"
                "Troubleshooting:\n"
                "1. Ensure Chrome is installed\n"
                "2. Try: pip install --upgrade undetected-chromedriver\n"
                "3. Check Chrome version matches ChromeDriver version\n"
                "4. Review logs for more details"
            ) from e


# Global browser config instance
_browser_config = None


def get_browser_config(chrome_path=None, headless=None, profile_dir=None):
    """Get or create the global browser configuration"""
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    return _browser_config


# ============================================================
# GEMINI INTERACTION
# ============================================================

def ask_gemini(prompt: str, chrome_path: str = None, headless: bool = None) -> str:
    """
    Send prompt to Gemini using undetected-chromedriver
    
    Args:
        prompt: Text prompt to send to Gemini
        chrome_path: Optional override for Chrome binary path
        headless: Optional override for headless mode
        
    Returns:
        str: Response from Gemini
    """
    driver = None
    
    try:
        logger.info("=== NEW GEMINI REQUEST ===")
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        # Get browser config with optional overrides
        try:
            config = get_browser_config(chrome_path, headless)
        except FileNotFoundError as e:
            logger.error(f"Chrome validation failed: {e}")
            return f"ERROR: {e}"
        
        # Launch browser
        try:
            driver = config.get_driver()
        except RuntimeError as e:
            logger.error(f"Driver creation failed: {e}")
            return f"ERROR: {e}"
        
        # Navigate to Gemini
        logger.info(f"Navigating to {GEMINI_URL}")
        driver.get(GEMINI_URL)
        
        # Wait for page to load
        time.sleep(5)
        
        # Check if user needs to log in by looking for the "Sign in" anchor tag or URL redirect
        current_url = driver.current_url
        sign_in_buttons = driver.find_elements(By.CSS_SELECTOR, 'a[aria-label="Sign in"]')
        
        needs_login = False
        if sign_in_buttons or "accounts.google.com" in current_url:
            needs_login = True
            
        if needs_login:
            logger.info("Login required. Switching to visible browser...")
            driver.quit()
            
            # VERY IMPORTANT: Chrome takes a few seconds to release the profile directory lock.
            # If we restart immediately, undetected-chromedriver will fall back to a temporary profile!
            logger.info("Waiting 5s for Chrome to release the profile lock...")
            time.sleep(5)
            
            # Switch to a visible browser for manual login
            original_headless = config.headless
            config.headless = False
            driver = config.get_driver()
            
            logger.info("Navigating to accounts.google.com for manual login")
            driver.get("https://accounts.google.com")
            
            logger.info("Waiting up to 5 minutes for user login (title exactly 'Google Account' or 'Google Accounts')...")
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
                
            logger.info("Login successful! Navigating back to Gemini in this visible window...")
            driver.get(GEMINI_URL)
            time.sleep(5)
            
            # Restore headless setting for the NEXT tool call
            config.headless = original_headless
            
        # Wait for input field
        logger.debug("Waiting for input field...")
        try:
            input_field = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-placeholder="Ask Gemini"]'))
            )
        except Exception as e:
            logger.error(f"Could not find input field: {e}")
            return f"ERROR: Failed to locate input field on Gemini page. {e}"
        
        # Add random delay
        random_delay(500, 1000)
        # Clean prompt of special characters that trigger premature submission
        prompt = prompt.replace('\n', ' ').replace('\r', '')
        
        # Type prompt
        if USE_HUMAN_TYPING:
            logger.info("Using human-like typing")
            human_type(input_field, prompt, TYPING_DELAY_MIN, TYPING_DELAY_MAX, TYPO_PROBABILITY)
        else:
            logger.info("Using standard typing")
            for char in prompt:
                input_field.send_keys(char)
                time.sleep(0.01)
        
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
                            "name": "query_premium_model",
                            "description": "Submits a complex prompt to the Gemini Large Language Model via a stealth browser. Use this tool when you need deep reasoning, generated text, code completion, or data analysis. Trigger keywords: TL;DR, summarize, solve, brainstorm. Do NOT use this tool for reading local files, simple OS queries, or trivial calculations.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "The exact text prompt to send to Gemini. Be extremely explicit and comprehensive. Examples: 'Write a python script to...', 'Summarize this log...'"
                                    },
                                    "chrome_path": {
                                        "type": "string",
                                        "description": "Absolute system path to the local Google Chrome executable. Use this only if automatic chrome detection fails."
                                    },
                                    "headless": {
                                        "type": "boolean",
                                        "description": "Run the browser invisibly. Set strictly to false if you suspect the browser requires manual human interaction for a login challenge."
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
                
                if tool_name == "query_premium_model":
                    prompt = arguments.get("prompt", "")
                    chrome_path = arguments.get("chrome_path")
                    headless = arguments.get("headless")
                    
                    # Run in thread to avoid blocking
                    output = await asyncio.to_thread(ask_gemini, prompt, chrome_path, headless)
                    
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


# ============================================================
# CLI ARGUMENT PARSING
# ============================================================
def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Gemini MCP Server using undetected-chromedriver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ENVIRONMENT VARIABLES:
  CHROME_PATH          Path to Chrome executable (use --chrome-path to override)

EXAMPLES:
  # Run MCP server with auto-detected Chrome
  python undetected_mcp.py
  
  # Specify Chrome path explicitly
  python undetected_mcp.py --chrome-path "/path/to/chrome"
  
  # Test Chrome detection and exit
  python undetected_mcp.py --check-chrome
  
  # Install/upgrade dependencies
  python undetected_mcp.py --install-deps
        """
    )
    
    parser.add_argument(
        "--chrome-path",
        help="Path to Chrome executable (auto-detected if not provided)"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode"
    )
    
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run Chrome in windowed mode (default)"
    )
    
    parser.add_argument(
        "--profile-dir",
        help="Custom Chrome profile directory"
    )
    
    parser.add_argument(
        "--check-chrome",
        action="store_true",
        help="Check Chrome installation and exit"
    )
    
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install/upgrade required Python packages and exit"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


def install_dependencies():
    """Install or upgrade required packages"""
    packages = [
        "undetected-chromedriver>=3.5.0",
        "selenium",
        "setuptools>=65.0.0"
    ]
    
    logger.info("Installing Python dependencies...")
    for package in packages:
        logger.info(f"  Installing {package}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                stdout=subprocess.DEVNULL if not logger.isEnabledFor(logging.DEBUG) else None,
                stderr=subprocess.STDOUT
            )
            logger.info(f"    ✓ {package}")
        except subprocess.CalledProcessError as e:
            logger.error(f"    ✗ Failed to install {package}: {e}")
            return False
    
    logger.info("✓ All dependencies installed successfully")
    return True


# ============================================================
# ENTRY POINT
# ============================================================
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        # Parse CLI arguments
        args = parse_args()
        
        # Handle --install-deps
        if args.install_deps:
            if install_dependencies():
                sys.exit(0)
            else:
                sys.exit(1)
        
        # Handle --check-chrome
        if args.check_chrome:
            logger.info("Checking Chrome installation...")
            try:
                chrome_path = validate_chrome(args.chrome_path)
                logger.info(f"✓ Chrome found at: {chrome_path}")
                sys.exit(0)
            except FileNotFoundError as e:
                logger.error(f"✗ {e}")
                sys.exit(1)
        
        # Initialize browser config with CLI overrides
        logger.info("Initializing MCP server...")
        headless = None
        if args.headless:
            headless = True
        elif args.no_headless:
            headless = False
        
        profile_dir = Path(args.profile_dir) if args.profile_dir else None
        get_browser_config(args.chrome_path, headless, profile_dir)
        
        # Run MCP server
        logger.info("Starting MCP server (undetected-chromedriver)")
        asyncio.run(mcp_server())
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down.")
        sys.exit(0)
    except FileNotFoundError as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
