"""
Browser Pool Manager - Core component for resource optimization.

Manages a pool of browser instances with tab-based isolation for minimum latency.
Supports lazy spawning, parallel execution, and automatic cleanup.
"""
import asyncio
import time
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BrowserSlot:
    """Represents a browser instance with its tabs."""
    browser: any  # WebDriver instance
    browser_id: int
    active_tabs: Dict[str, float]  # tab_handle -> last_used_timestamp
    created_at: float
    request_count: int = 0


@dataclass
class PoolStats:
    """Statistics about the browser pool."""
    total_browsers: int
    active_tabs: int
    queued_requests: int
    total_requests_processed: int


class BrowserPool:
    """Manages a pool of browser instances with tab-based isolation.

    Features:
    - Lazy browser spawning (start with 0 browsers)
    - Parallel tab execution (up to 10 concurrent requests)
    - Automatic cleanup of idle tabs and browsers
    - Thread-safe for multiple IDE clients
    """

    def __init__(
        self,
        max_browsers: int = 2,
        max_tabs_per_browser: int = 5,
        tab_idle_timeout: int = 300,
        browser_idle_timeout: int = 1800,
        lazy_spawn: bool = True
    ):
        self.max_browsers = max_browsers
        self.max_tabs_per_browser = max_tabs_per_browser
        self.tab_idle_timeout = tab_idle_timeout
        self.browser_idle_timeout = browser_idle_timeout
        self.lazy_spawn = lazy_spawn

        self.browsers: List[BrowserSlot] = []
        self.queue: asyncio.Queue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.total_requests = 0

        # Start cleanup task
        self._cleanup_task = None

        logger.info(
            f"Browser pool initialized: max_browsers={max_browsers}, "
            f"max_tabs={max_tabs_per_browser}, lazy_spawn={lazy_spawn}"
        )

    async def start(self):
        """Start the browser pool and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Browser pool started")

    async def stop(self):
        """Stop the browser pool and close all browsers."""
        logger.info("Stopping browser pool...")

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all browsers
        async with self.lock:
            for slot in self.browsers:
                try:
                    await asyncio.to_thread(slot.browser.quit)
                    logger.info(f"Closed browser {slot.browser_id}")
                except Exception as e:
                    logger.error(f"Error closing browser {slot.browser_id}: {e}")

            self.browsers.clear()

        logger.info("Browser pool stopped")

    async def execute_task(self, adapter, prompt: str, model: str, **kwargs):
        """Execute task using pooled browser tab.

        Strategy for minimum latency:
        1. Check if slot available (browser with <5 tabs)
        2. If yes: Execute immediately in parallel
        3. If no (all 10 slots busy): Queue and wait

        Args:
            adapter: The adapter instance to use
            prompt: The prompt to send
            model: The model to use
            **kwargs: Additional arguments for the adapter

        Returns:
            The response from the adapter
        """
        self.total_requests += 1
        request_id = self.total_requests

        logger.info(f"Request {request_id}: Acquiring browser slot...")

        # Get available slot (may wait in queue if all busy)
        browser, tab_handle = await self._get_available_slot()

        try:
            logger.info(
                f"Request {request_id}: Executing on browser {browser.browser_id}, "
                f"tab {tab_handle}"
            )

            # Execute adapter with pooled browser
            result = await asyncio.to_thread(
                adapter.process,
                prompt,
                model,
                driver=browser.browser,
                tab_handle=tab_handle,
                **kwargs
            )

            logger.info(f"Request {request_id}: Completed successfully")
            return result

        except Exception as e:
            logger.error(f"Request {request_id}: Failed with error: {e}", exc_info=True)
            raise

        finally:
            # Release slot back to pool
            await self._release_slot(browser, tab_handle)

    async def _get_available_slot(self) -> Tuple[BrowserSlot, str]:
        """Get available (browser, tab) slot.

        Returns immediately if slot available.
        Waits in queue if all slots busy.
        """
        async with self.lock:
            # Try to find browser with available capacity
            for browser_slot in self.browsers:
                if len(browser_slot.active_tabs) < self.max_tabs_per_browser:
                    # Found available slot
                    try:
                        tab_handle = await self._create_new_tab(browser_slot)
                        return browser_slot, tab_handle
                    except Exception as e:
                        logger.error(f"Failed to create tab in browser {browser_slot.browser_id}: {e}")
                        # Browser might be dead, try next one
                        continue

            # No available slots in existing browsers
            # Try to create new browser if under limit
            if len(self.browsers) < self.max_browsers:
                browser_slot = await self._spawn_browser()
                tab_handle = await self._create_new_tab(browser_slot)
                return browser_slot, tab_handle

        # All slots busy - wait in queue
        logger.info(f"All {self.max_browsers * self.max_tabs_per_browser} slots busy, queuing request...")

        # Wait for a slot to become available
        while True:
            await asyncio.sleep(0.5)  # Check every 500ms

            async with self.lock:
                for browser_slot in self.browsers:
                    if len(browser_slot.active_tabs) < self.max_tabs_per_browser:
                        try:
                            tab_handle = await self._create_new_tab(browser_slot)
                            logger.info("Slot became available, resuming queued request")
                            return browser_slot, tab_handle
                        except Exception as e:
                            logger.error(f"Failed to create tab: {e}")
                            continue

    async def _spawn_browser(self) -> BrowserSlot:
        """Spawn a new browser instance.

        Returns:
            BrowserSlot instance
        """
        browser_id = len(self.browsers) + 1
        logger.info(f"Spawning browser {browser_id}...")

        try:
            # Import here to avoid circular dependency
            from mcp_manager.browser import get_browser_config

            config = get_browser_config()
            browser = await asyncio.to_thread(config.get_driver)

            slot = BrowserSlot(
                browser=browser,
                browser_id=browser_id,
                active_tabs={},
                created_at=time.time()
            )

            self.browsers.append(slot)
            logger.info(f"Browser {browser_id} spawned successfully")

            return slot

        except Exception as e:
            logger.error(f"Failed to spawn browser {browser_id}: {e}", exc_info=True)
            raise

    async def _create_new_tab(self, browser_slot: BrowserSlot) -> str:
        """Create a new tab in the browser.

        Args:
            browser_slot: The browser slot to create tab in

        Returns:
            Tab handle (window handle)
        """
        try:
            # Check if browser is still alive
            try:
                await asyncio.to_thread(lambda: browser_slot.browser.current_url)
            except Exception as e:
                logger.warning(f"Browser {browser_slot.browser_id} appears dead, respawning...")
                # Remove dead browser from pool
                self.browsers.remove(browser_slot)
                # Spawn new browser
                new_browser = await self._spawn_browser()
                # Update reference
                browser_slot = new_browser

            # Open new tab
            await asyncio.to_thread(
                browser_slot.browser.execute_script,
                "window.open('about:blank', '_blank');"
            )

            # Get the new tab handle
            handles = await asyncio.to_thread(lambda: browser_slot.browser.window_handles)
            new_handle = handles[-1]

            # Track the tab
            browser_slot.active_tabs[new_handle] = time.time()
            browser_slot.request_count += 1

            logger.debug(
                f"Created new tab {new_handle} in browser {browser_slot.browser_id}. "
                f"Active tabs: {len(browser_slot.active_tabs)}"
            )

            return new_handle

        except Exception as e:
            logger.error(f"Failed to create new tab: {e}", exc_info=True)
            raise

    async def _release_slot(self, browser_slot: BrowserSlot, tab_handle: str):
        """Release slot back to pool after task completes.

        Args:
            browser_slot: The browser slot
            tab_handle: The tab handle to release
        """
        async with self.lock:
            if tab_handle in browser_slot.active_tabs:
                # Update last used time
                browser_slot.active_tabs[tab_handle] = time.time()

                logger.debug(
                    f"Released tab {tab_handle} in browser {browser_slot.browser_id}. "
                    f"Active tabs: {len(browser_slot.active_tabs)}"
                )

    async def _cleanup_loop(self):
        """Background task to cleanup idle tabs and browsers."""
        logger.info("Cleanup loop started")

        try:
            while True:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle_resources()

        except asyncio.CancelledError:
            logger.info("Cleanup loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Cleanup loop error: {e}", exc_info=True)

    async def _cleanup_idle_resources(self):
        """Cleanup idle tabs and browsers."""
        current_time = time.time()

        async with self.lock:
            browsers_to_remove = []

            for browser_slot in self.browsers:
                tabs_to_close = []

                # Find idle tabs
                for tab_handle, last_used in browser_slot.active_tabs.items():
                    if current_time - last_used > self.tab_idle_timeout:
                        tabs_to_close.append(tab_handle)

                # Close idle tabs
                for tab_handle in tabs_to_close:
                    try:
                        await asyncio.to_thread(
                            browser_slot.browser.switch_to.window,
                            tab_handle
                        )
                        await asyncio.to_thread(browser_slot.browser.close)
                        del browser_slot.active_tabs[tab_handle]

                        logger.info(
                            f"Closed idle tab {tab_handle} in browser {browser_slot.browser_id}"
                        )
                    except Exception as e:
                        logger.error(f"Error closing tab {tab_handle}: {e}")

                # Check if browser is idle (no active tabs)
                if (len(browser_slot.active_tabs) == 0 and
                    current_time - browser_slot.created_at > self.browser_idle_timeout):
                    browsers_to_remove.append(browser_slot)

            # Close idle browsers
            for browser_slot in browsers_to_remove:
                try:
                    await asyncio.to_thread(browser_slot.browser.quit)
                    self.browsers.remove(browser_slot)

                    logger.info(
                        f"Closed idle browser {browser_slot.browser_id} "
                        f"(idle for {int(current_time - browser_slot.created_at)}s)"
                    )
                except Exception as e:
                    logger.error(f"Error closing browser {browser_slot.browser_id}: {e}")

    def get_stats(self) -> PoolStats:
        """Get current pool statistics.

        Returns:
            PoolStats instance
        """
        total_tabs = sum(len(b.active_tabs) for b in self.browsers)

        return PoolStats(
            total_browsers=len(self.browsers),
            active_tabs=total_tabs,
            queued_requests=self.queue.qsize(),
            total_requests_processed=self.total_requests
        )
