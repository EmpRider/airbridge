"""
Configuration for Gemini MCP Server using undetected-chromedriver
"""
import os
import platform
from pathlib import Path

# Base directories
BASE_DIR = Path.home() / "web-proxy"
CHROME_PROFILE_DIR = BASE_DIR / "chrome-profile"
LOG_FILE = BASE_DIR / "gemini_mcp.log"

# Ensure directories exist
BASE_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Gemini configuration
GEMINI_URL = "https://gemini.google.com/app"

# Timeout configuration (1 hour for long responses)
SCRIPT_TIMEOUT = 3600  # 1 hour in seconds
PAGE_LOAD_TIMEOUT = 60  # 60 seconds
IMPLICIT_WAIT = 10  # 10 seconds

# Browser configuration
USE_HEADLESS = False  # Set to False for first login, then True
WINDOW_SIZE = (1920, 1080)

# Human-like typing
USE_HUMAN_TYPING = True  # Type with random delays
TYPING_DELAY_MIN = 0.01  # Minimum delay between keystrokes (seconds) - faster
TYPING_DELAY_MAX = 0.03  # Maximum delay between keystrokes (seconds) - faster
TYPO_PROBABILITY = 0.02  # 2% chance of typo + correction - less typos

# Response polling
POLL_INTERVAL = 1.0  # Check for response every 1 second
STABLE_CHECKS = 3  # Response must be stable for 3 checks
MIN_RESPONSE_LENGTH = 20  # Minimum characters before considering response

# Chrome binary location
def get_chrome_path():
    """
    Auto-detect Chrome installation path
    
    Returns:
        str: Path to Chrome executable, or None if not found
    """
    if platform.system() == "Windows":
        paths = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"
        ]
        for path in paths:
            if path.exists():
                return str(path)
    elif platform.system() == "Darwin":  # macOS
        path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if path.exists():
            return str(path)
    else:  # Linux
        paths = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium")
        ]
        for path in paths:
            if path.exists():
                return str(path)
    return None

# Allow override via environment variable
CHROME_BINARY_PATH = os.getenv("CHROME_PATH") or get_chrome_path()
