"""
Configuration for Gemini MCP Server using undetected-chromedriver
"""
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
