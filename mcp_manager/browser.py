"""
Browser management - Playwright integration for high-concurrency sessions.

Design notes:
- Uses Playwright's async API for native parallelism.
- Implements Persistent Contexts for session persistence (cookies/storage).
"""
import os
import logging
import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# ============================================================
# DEFAULT BROWSER SETTINGS
# ============================================================
BASE_DIR = Path.home() / "web-proxy"
CHROME_PROFILE_DIR = BASE_DIR / "playwright-profiles"
LOG_FILE = BASE_DIR / "gemini_mcp.log"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Playwright defaults
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
USE_HEADLESS = True

# Allow override via environment variable
CHROME_BINARY_PATH = os.getenv("CHROME_PATH", None)

class BrowserConfig:
    """Holds server *default* browser settings for Playwright."""

    def __init__(self, chrome_path=None, headless=None, profile_dir=None):
        self.chrome_path = chrome_path
        self.headless = headless if headless is not None else USE_HEADLESS
        self.profile_dir = Path(profile_dir) if profile_dir else CHROME_PROFILE_DIR
        self._playwright = None
        self._browser = None

    async def get_browser(self):
        """Initialize and return the singleton Playwright browser instance."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            launch_options = {
                "headless": self.headless,
                "args": ["--disable-blink-features=AutomationControlled"]
            }
            if self.chrome_path:
                launch_options["executable_path"] = self.chrome_path
            
            self._browser = await self._playwright.chromium.launch(**launch_options)
            logger.info(f"Playwright browser launched (headless={self.headless})")
        return self._browser

    async def close_browser(self):
        """Gracefully shut down the browser and playwright instance."""
        if self._browser:
            await self._browser.close()
            await self._playwright.stop()
            self._browser = None
            self._playwright = None
            logger.info("Playwright browser shut down")

    async def create_context(self, profile_subdir: Optional[str] = None, headless_override: Optional[bool] = None):
        """
        Create an isolated browser context. 
        If profile_subdir is provided, uses a persistent context (for logins).
        """
        # Ensure playwright is initialized
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        
        if profile_subdir:
            user_data_dir = self.profile_dir / profile_subdir
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Persistent contexts launch their own browser process
            launch_options = {
                "user_data_dir": str(user_data_dir),
                "headless": headless_override if headless_override is not None else self.headless,
                "viewport": DEFAULT_VIEWPORT,
                "args": ["--disable-blink-features=AutomationControlled"]
            }
            if self.chrome_path:
                launch_options["executable_path"] = self.chrome_path
            
            context = await self._playwright.chromium.launch_persistent_context(**launch_options)
            return context
        else:
            # Ephemeral context using the singleton browser
            browser = await self.get_browser()
            context = await browser.new_context(viewport=DEFAULT_VIEWPORT)
            return context

# Singleton pattern for the *default* browser config
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
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    else:
        if chrome_path is not None:
            _browser_config.chrome_path = chrome_path
        if headless is not None:
            _browser_config.headless = headless
        if profile_dir is not None:
            _browser_config.profile_dir = Path(profile_dir)
    return _browser_config

def reset_browser_config():
    global _browser_config
    _browser_config = None
