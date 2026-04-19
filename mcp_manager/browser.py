"""
Browser management - Playwright integration for high-concurrency sessions.

Design notes:
- Uses Playwright's async API for native parallelism.
- Implements Persistent Contexts for session persistence (cookies/storage).
"""
import os
import logging
import asyncio
import shutil
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# ============================================================
# DEFAULT BROWSER SETTINGS
# ============================================================
BASE_DIR = Path.home() / "web-proxy"
CHROME_PROFILE_DIR = BASE_DIR / "playwright-profiles"
GOLDEN_PROFILE_DIR = CHROME_PROFILE_DIR / "_golden"
LOG_FILE = BASE_DIR / "gemini_mcp.log"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Playwright defaults
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
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
        # Add a lock to prevent concurrent redundant browser instantiations
        self._lock = asyncio.Lock()

    async def get_browser(self):
        """Initialize and return the singleton Playwright browser instance."""
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            
            if self._browser is None:
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
        async with self._lock:
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
        async with self._lock:
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


# ============================================================
# GOLDEN PROFILE UTILITIES
# ============================================================

# Lock files that Chromium holds while running — skip during copy
_LOCK_FILE_NAMES = {"SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"}


def _is_lock_file(name: str) -> bool:
    return name in _LOCK_FILE_NAMES or name.endswith(".lock")


def _ignore_lock_files(directory, contents):
    return [c for c in contents if _is_lock_file(c)]


def golden_profile_exists() -> bool:
    """Check if a golden profile with session data exists."""
    if not GOLDEN_PROFILE_DIR.is_dir():
        return False
    # Must have at least some content (not just an empty dir)
    return any(GOLDEN_PROFILE_DIR.iterdir())


async def copy_profile(src: Path, dst: Path):
    """Copy a browser profile directory, skipping Chromium lock files."""
    try:
        if not src.is_dir():
            logger.warning(f"Source profile does not exist: {src}")
            return False
        dst.mkdir(parents=True, exist_ok=True)
        # Using asyncio.to_thread to prevent blocking the event loop with synchronous file I/O
        await asyncio.to_thread(shutil.copytree, str(src), str(dst), dirs_exist_ok=True, ignore=_ignore_lock_files)
        logger.info(f"Profile copied: {src} -> {dst}")
        return True
    except Exception as e:
        logger.error(f"Failed to copy profile {src} -> {dst}: {e}")
        return False


async def cleanup_pool_profiles():
    """Delete stale pool_* profile directories left from previous runs."""
    try:
        for entry in CHROME_PROFILE_DIR.iterdir():
            if entry.is_dir() and entry.name.startswith("pool_"):
                # Using asyncio.to_thread to prevent blocking the event loop with synchronous file I/O
                await asyncio.to_thread(shutil.rmtree, str(entry), ignore_errors=True)
                logger.debug(f"Cleaned up stale pool profile: {entry.name}")
    except Exception as e:
        logger.warning(f"Error during pool profile cleanup: {e}")
