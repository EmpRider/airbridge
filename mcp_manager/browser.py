"""
Browser management - Chrome detection, validation, and WebDriver creation.

Design notes:
- BrowserConfig is now a *defaults holder* — it stores server-default settings.
- get_driver(headless=..., profile_dir=...) accepts overrides per call so the
  pool can spawn browsers with different headless modes for different requests.
- Chrome validation is LAZY (deferred until get_driver is called) so a missing
  Chrome doesn't crash the server during startup.
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
IMPLICIT_WAIT = 0
USE_HEADLESS = True
WINDOW_SIZE = (1920, 1080)

USE_HUMAN_TYPING = True
TYPING_DELAY_MIN = 0.00001
TYPING_DELAY_MAX = 0.00005
TYPO_PROBABILITY = 0.0002

POLL_INTERVAL = 0.1
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
    """Holds server *default* browser settings.

    Important: this object stores DEFAULTS only. Each call to get_driver()
    can override headless / profile_dir on a per-instance basis. Chrome path
    validation is deferred to first use so server startup never crashes
    on a missing Chrome binary.
    """

    def __init__(self, chrome_path=None, headless=None, profile_dir=None):
        self.chrome_path = chrome_path  # None means "auto-detect later"
        self.headless = headless if headless is not None else USE_HEADLESS
        self.profile_dir = profile_dir or CHROME_PROFILE_DIR
        self._chrome_executable = None  # validated lazily
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create profile dir {self.profile_dir}: {e}")

    @property
    def chrome_executable(self):
        """Lazily resolve the Chrome path. Raises FileNotFoundError if missing."""
        if self._chrome_executable is None:
            self._chrome_executable = validate_chrome(self.chrome_path)
        return self._chrome_executable

    def get_driver(self, headless=None, profile_subdir=None):
        """Create an undetected Chrome driver.

        Args:
            headless: per-call override; if None falls back to self.headless
            profile_subdir: optional subdirectory under self.profile_dir to
                isolate this browser's profile (avoids "user-data-dir already
                in use" errors when multiple browsers run from one pool).
        """
        import undetected_chromedriver as uc

        # Resolve effective settings
        effective_headless = self.headless if headless is None else headless

        if profile_subdir:
            effective_profile = self.profile_dir / profile_subdir
            effective_profile.mkdir(parents=True, exist_ok=True)
        else:
            effective_profile = self.profile_dir

        chrome_exe = self.chrome_executable  # raises if missing

        try:
            logger.info(
                f"Launching Chrome (headless={effective_headless}, "
                f"profile={effective_profile.name})..."
            )
            options = uc.ChromeOptions()
            options.binary_location = chrome_exe
            options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')

            if effective_headless:
                options.add_argument('--headless=new')

            # Resource optimization (kept conservative — nothing destructive)
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-sync')
            options.add_argument('--metrics-recording-only')
            options.add_argument('--mute-audio')

            # NOTE: We do NOT set --remote-debugging-port. undetected_chromedriver
            # manages its own debugging port and overriding it causes connection
            # failures.

            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.managed_default_content_settings.fonts": 2,
            }
            options.add_experimental_option("prefs", prefs)

            driver = uc.Chrome(
                options=options,
                user_data_dir=str(effective_profile),
                version_main=None,
                driver_executable_path=None,
                browser_executable_path=chrome_exe,
            )
            driver.set_script_timeout(SCRIPT_TIMEOUT)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(IMPLICIT_WAIT)

            # Tag the driver with its mode for later identification by the pool
            try:
                driver._wp_headless = effective_headless
                driver._wp_profile = str(effective_profile)
            except Exception:
                pass

            logger.info("Chrome launched successfully")
            return driver
        except Exception as e:
            logger.error(f"Failed to create WebDriver: {e}", exc_info=True)
            raise RuntimeError(f"ChromeDriver creation failed: {e}") from e


# Singleton pattern for the *default* browser config (server-wide)
_browser_config = None

# Global temp chat preference
_use_temp_chat = True


def set_temp_chat_preference(use_temp_chat):
    """Set the global temp chat preference."""
    global _use_temp_chat
    _use_temp_chat = use_temp_chat
    logger.info(f"Temp chat preference set to: {use_temp_chat}")


def get_temp_chat_preference():
    """Get the global temp chat preference."""
    return _use_temp_chat


def get_browser_config(chrome_path=None, headless=None, profile_dir=None):
    """Get or create the server-wide default browser configuration.

    If config already exists, updates it with any non-None parameters.
    Per-request overrides should be passed to BrowserConfig.get_driver()
    instead of mutating this singleton.
    """
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    else:
        if chrome_path is not None:
            _browser_config.chrome_path = chrome_path
            _browser_config._chrome_executable = None  # force re-validation
        if headless is not None:
            _browser_config.headless = headless
        if profile_dir is not None:
            _browser_config.profile_dir = profile_dir
            try:
                _browser_config.profile_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not create profile dir: {e}")
    return _browser_config


def reset_browser_config():
    """Reset the singleton (used for testing / explicit reload)."""
    global _browser_config
    _browser_config = None
