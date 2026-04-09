"""
Configuration module for Playwright-based MCP server
Centralized settings for browser automation and anti-detection
"""
from pathlib import Path

# Base directories
BASE_DIR = Path.home() / "web-proxy"
BROWSER_STATE_DIR = BASE_DIR / "browser_state"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
LOG_FILE = BASE_DIR / "mcp_playwright.log"

# User data directory (use existing Chrome profile to avoid login issues)
# Set to None to use storage_state (recommended - works with login_helper.py)
# Set to a path to use persistent profile directory
USER_DATA_DIR = None  # Use storage_state approach (login via login_helper.py)

# Ensure directories exist
BASE_DIR.mkdir(parents=True, exist_ok=True)
BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
if USER_DATA_DIR:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Gemini configuration
GEMINI_URL = "https://gemini.google.com/app"

# Timeout configuration (1 hour for long responses)
SCRIPT_TIMEOUT = 3600000  # 1 hour in milliseconds
PAGE_TIMEOUT = 3600000    # 1 hour in milliseconds
NAVIGATION_TIMEOUT = 60000  # 60 seconds in milliseconds

# Browser configuration
# IMPORTANT: Set to False for first-time login to see UI and log in manually
# After login is saved, change to True for headless operation
USE_HEADLESS = True  # False = Show browser UI, True = Headless mode
BROWSER_CHANNEL = "chrome"  # Use Chrome for best compatibility

# Stealth configuration (Expert recommendations)
BLOCK_TELEMETRY = True  # Block analytics and tracking
USE_HUMAN_TYPING = True  # Use human-like typing patterns
RANDOMIZE_HARDWARE = True  # Randomize hardware fingerprint

# User agent and headers (must match Chrome 120)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SEC_CH_UA = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
SEC_CH_UA_MOBILE = "?0"
SEC_CH_UA_PLATFORM = '"Windows"'

# Hardware fingerprint (realistic consumer device)
HARDWARE_CONCURRENCY = 8  # 8 CPU cores
DEVICE_MEMORY = 8  # 8GB RAM

# Viewport configuration
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080

# Locale and timezone
LOCALE = "en-US"
TIMEZONE_ID = "America/New_York"
