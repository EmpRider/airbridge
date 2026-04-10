"""
Browser management - Chrome detection, validation, and WebDriver creation.
Extracted from the original undetected_mcp.py monolith.
"""
import os
import sys
import platform
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# DEFAULT BROWSER SETTINGS
# ============================================================
BASE_DIR = Path.home() / "web-proxy"
CHROME_PROFILE_DIR = BASE_DIR / "chrome-profile"
LOG_FILE = BASE_DIR / "gemini_mcp.log"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

SCRIPT_TIMEOUT = 3600
PAGE_LOAD_TIMEOUT = 60
IMPLICIT_WAIT = 10
USE_HEADLESS = True
WINDOW_SIZE = (1920, 1080)

USE_HUMAN_TYPING = True
TYPING_DELAY_MIN = 0.00001
TYPING_DELAY_MAX = 0.00005
TYPO_PROBABILITY = 0.0002

POLL_INTERVAL = 1.0
STABLE_CHECKS = 3
MIN_RESPONSE_LENGTH = 20

# Allow override via environment variable
CHROME_BINARY_PATH = os.getenv("CHROME_PATH", None)


def find_chrome_executable():
    """Detect Chrome installation across OS platforms."""
    for cmd in ["google-chrome", "chrome", "chromium", "chromium-browser"]:
        path = shutil.which(cmd)
        if path:
            logger.debug(f"Found Chrome via PATH: {path}")
            return path

    system = platform.system()
    if system == "Windows":
        possible_paths = [
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            f"{Path.home()}/AppData/Local/Google/Chrome/Application/chrome.exe",
            "C:/Program Files/Chromium/Application/chrome.exe",
        ]
    elif system == "Darwin":
        possible_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
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


def validate_chrome(chrome_path=None):
    """Validate Chrome installation and return valid path."""
    if chrome_path:
        path = Path(chrome_path)
        if path.exists() and path.is_file():
            logger.info(f"Chrome found at: {chrome_path}")
            return str(chrome_path)
        else:
            raise FileNotFoundError(f"Chrome not found at: {chrome_path}")

    if CHROME_BINARY_PATH:
        path = Path(CHROME_BINARY_PATH)
        if path.exists():
            logger.info(f"Using Chrome from env: {CHROME_BINARY_PATH}")
            return CHROME_BINARY_PATH

    detected = find_chrome_executable()
    if detected:
        logger.info(f"Chrome auto-detected at: {detected}")
        return detected

    raise FileNotFoundError(
        "Chrome not found!\n\n"
        "Install Google Chrome: https://www.google.com/chrome/\n\n"
        "Or specify its path:\n"
        "  Option 1: Set CHROME_PATH environment variable\n"
        "  Option 2: Pass --chrome-path argument\n"
    )


class BrowserConfig:
    """Centralized browser configuration with CLI override support."""

    def __init__(self, chrome_path=None, headless=None, profile_dir=None):
        self.chrome_path = chrome_path
        self.headless = headless if headless is not None else USE_HEADLESS
        self.profile_dir = profile_dir or CHROME_PROFILE_DIR
        self.chrome_executable = validate_chrome(self.chrome_path)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def get_driver(self):
        """Create undetected Chrome driver with validated configuration."""
        import undetected_chromedriver as uc

        try:
            logger.info(f"Launching Chrome (headless={self.headless})...")
            options = uc.ChromeOptions()
            options.binary_location = self.chrome_executable
            options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')

            driver = uc.Chrome(
                options=options,
                user_data_dir=str(self.profile_dir),
                version_main=None,
                driver_executable_path=None,
                browser_executable_path=self.chrome_executable
            )
            driver.set_script_timeout(SCRIPT_TIMEOUT)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(IMPLICIT_WAIT)
            logger.info("Chrome launched successfully")
            return driver
        except Exception as e:
            logger.error(f"Failed to create WebDriver: {e}", exc_info=True)
            raise RuntimeError(f"ChromeDriver creation failed: {e}") from e


# Singleton pattern for global browser config
_browser_config = None


def get_browser_config(chrome_path=None, headless=None, profile_dir=None):
    """Get or create the global browser configuration."""
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    return _browser_config
