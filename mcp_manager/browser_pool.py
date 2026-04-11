"""
Browser Pool Manager — maintains browser instances tagged by headless mode.

Each BrowserSlot carries its headless mode; requests that specify an explicit
headless setting only reuse browsers that match. This means one server can
serve both headless and windowed Chrome for different clients/requests.
"""
import asyncio
import time
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BrowserSlot:
    """Represents a browser instance with its tabs."""
    browser: any  # WebDriver instance
    browser_id: int
    headless: bool                         # the mode this browser runs in
    active_tabs: Dict[str, float] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    request_count: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class PoolStats:
    total_browsers: int
    active_tabs: int
    queued_requests: int
    total_requests_processed: int


class BrowserPool:
    """Manages browser instances with tab-based isolation + headless-mode tagging."""

    def __init__(
        self,
        max_browsers: int = 2,
        max_tabs_per_browser: int = 5,
        tab_idle_timeout: int = 300,
        browser_idle_timeout: int = 1800,
        lazy_spawn: bool = True,
        default_headless: bool = True,
    ):
        self.max_browsers = max_browsers
        self.max_tabs_per_browser = max_tabs_per_browser
        self.tab_idle_timeout = tab_idle_timeout
        self.browser_idle_timeout = browser_idle_timeout
        self.lazy_spawn = lazy_spawn
        self.default_headless = default_headless

        self.browsers: List[BrowserSlot] = []
        self.lock = asyncio.Lock()
        self.pending_spawns = set()
        self.total_requests = 0
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(
            f"Browser pool initialized: max_browsers={max_browsers}, "
            f"max_tabs={max_tabs_per_browser}, lazy_spawn={lazy_spawn}, "
            f"default_headless={default_headless}"
        )

    async def start(self):
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Browser pool started")

    async def stop(self):
        logger.info("Stopping browser pool...")

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self.lock:
            for slot in self.browsers:
                try:
                    await self._safe_quit_browser(slot.browser)
                    logger.info(f"Closed browser {slot.browser_id}")
                except Exception as e:
                    logger.error(f"Error closing browser {slot.browser_id}: {e}")
            self.browsers.clear()

        logger.info("Browser pool stopped")

    async def _safe_quit_browser(self, browser):
        """Quit a browser; only touch processes this driver owns."""
        try:
            await asyncio.to_thread(browser.quit)
            return
        except Exception as e:
            logger.warning(f"Graceful browser.quit() failed: {e}")

        # Fall back: use the driver's own service.process to kill its tree.
        # CRITICAL: we only kill PIDs we own — never a blanket chrome.exe kill.
        try:
            import psutil
            service = getattr(browser, "service", None)
            proc = getattr(service, "process", None) if service else None
            pid = getattr(proc, "pid", None) if proc else None
            if pid and psutil.pid_exists(pid):
                p = psutil.Process(pid)
                for child in p.children(recursive=True):
                    try:
                        child.kill()
                    except Exception:
                        pass
                try:
                    p.kill()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Force-kill of browser subprocess tree failed: {e}")

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------
    async def execute_task(
        self,
        adapter,
        prompt: str,
        model: str,
        headless: Optional[bool] = None,
        **kwargs,
    ):
        """Execute an adapter task on an available (or newly spawned) browser slot.

        Args:
            adapter: adapter instance with a .process() method
            prompt: prompt text
            model: model identifier
            headless: per-request override; None means "use pool default"
        """
        self.total_requests += 1
        request_id = self.total_requests

        effective_headless = (
            self.default_headless if headless is None else bool(headless)
        )

        logger.info(
            f"Request {request_id}: acquiring slot (headless={effective_headless})..."
        )

        browser_slot, tab_handle = await self._get_available_slot(effective_headless)

        try:
            logger.info(
                f"Request {request_id}: executing on browser "
                f"{browser_slot.browser_id} (headless={browser_slot.headless}), "
                f"tab {tab_handle}"
            )

            # adapter.process runs synchronously — dispatch to a thread.
            # Note: we do NOT pass headless to adapter.process — the browser
            # is already running in the requested mode.
            async with browser_slot.lock:
                result = await asyncio.to_thread(
                    adapter.process,
                    prompt,
                    model,
                    driver=browser_slot.browser,
                    tab_handle=tab_handle,
                    **kwargs,
                )

            logger.info(f"Request {request_id}: completed")
            return result

        except Exception as e:
            logger.error(f"Request {request_id}: failed: {e}", exc_info=True)
            raise
        finally:
            await self._release_slot(browser_slot, tab_handle)

    async def _get_available_slot(self, headless: bool) -> Tuple[BrowserSlot, str]:
        """Find or spawn a browser slot matching the requested headless mode."""
        async with self.lock:
            # Look for an existing matching-mode browser with capacity
            for slot in self.browsers:
                if slot.headless != headless:
                    continue
                if len(slot.active_tabs) >= self.max_tabs_per_browser:
                    continue
                # We release the lock to create the tab to avoid blocking others
                # but we keep the slot in mind. 
                # Actually, for tabs it's fast, but spawns are slow.
                try:
                    tab_handle = await self._create_new_tab(slot)
                    return slot, tab_handle
                except Exception as e:
                    logger.error(
                        f"Failed to create tab in browser {slot.browser_id}: {e}"
                    )
                    continue

            # Need a new browser — check cap including pending spawns
            if len(self.browsers) + len(self.pending_spawns) < self.max_browsers:
                spawn_id = uuid.uuid4()
                self.pending_spawns.add(spawn_id)
                logger.info(f"Reserved spawn slot {spawn_id}")
            else:
                # At capacity. Try evicting if no matching browser exists
                if not any(s.headless == headless for s in self.browsers):
                    evicted = await self._try_evict_one()
                    if evicted:
                        spawn_id = uuid.uuid4()
                        self.pending_spawns.add(spawn_id)
                        logger.info(f"Reserved spawn slot {spawn_id} after eviction")
                    else:
                        spawn_id = None
                else:
                    spawn_id = None

        if spawn_id:
            try:
                slot = await self._spawn_browser(headless)
                tab_handle = await self._create_new_tab(slot)
                return slot, tab_handle
            finally:
                async with self.lock:
                    self.pending_spawns.remove(spawn_id)

        # Pool is saturated with matching-mode browsers; wait for a slot.
        logger.info(
            f"All {self.max_browsers * self.max_tabs_per_browser} slots busy, "
            f"waiting for headless={headless} slot..."
        )
        while True:
            await asyncio.sleep(0.5)
            async with self.lock:
                for slot in self.browsers:
                    if slot.headless != headless:
                        continue
                    if len(slot.active_tabs) >= self.max_tabs_per_browser:
                        continue
                    try:
                        tab_handle = await self._create_new_tab(slot)
                        logger.info("Slot became available")
                        return slot, tab_handle
                    except Exception as e:
                        logger.error(f"Failed to create tab: {e}")

    async def _try_evict_one(self) -> bool:
        """Evict the most-idle browser with zero active tabs. Caller holds self.lock."""
        candidates = [s for s in self.browsers if not s.active_tabs]
        if not candidates:
            return False
        # Oldest first
        candidates.sort(key=lambda s: s.created_at)
        victim = candidates[0]
        try:
            await self._safe_quit_browser(victim.browser)
            self.browsers.remove(victim)
            logger.info(
                f"Evicted idle browser {victim.browser_id} (headless={victim.headless}) "
                f"to make room"
            )
            return True
        except Exception as e:
            logger.error(f"Eviction failed: {e}")
            return False

    async def _spawn_browser(self, headless: bool) -> BrowserSlot:
        """Spawn a new browser with the given headless mode. Caller holds self.lock."""
        browser_id = (max((s.browser_id for s in self.browsers), default=0) or 0) + 1
        logger.info(f"Spawning browser {browser_id} (headless={headless})...")

        try:
            from mcp_manager.browser import get_browser_config

            config = get_browser_config()
            # Per-browser profile dir to avoid "user-data-dir already in use"
            profile_subdir = f"browser_{browser_id}"
            browser = await asyncio.to_thread(
                config.get_driver,
                headless=headless,
                profile_subdir=profile_subdir,
            )

            slot = BrowserSlot(
                browser=browser,
                browser_id=browser_id,
                headless=headless,
            )
            self.browsers.append(slot)
            logger.info(f"Browser {browser_id} spawned (headless={headless})")
            return slot

        except Exception as e:
            logger.error(f"Failed to spawn browser {browser_id}: {e}", exc_info=True)
            raise

    async def _create_new_tab(self, slot: BrowserSlot) -> str:
        """Open a new tab on the given browser and return its handle."""
        try:
            # Lightweight liveness check — getattr, no network/automation call
            _ = await asyncio.to_thread(lambda: slot.browser.window_handles)
        except Exception as e:
            logger.warning(
                f"Browser {slot.browser_id} appears dead ({e}); removing from pool"
            )
            # Remove dead browser (caller will trigger respawn on retry)
            if slot in self.browsers:
                self.browsers.remove(slot)
            raise

        try:
            await asyncio.to_thread(
                slot.browser.execute_script,
                "window.open('about:blank', '_blank');",
            )
            handles = await asyncio.to_thread(lambda: slot.browser.window_handles)
            new_handle = handles[-1]
            slot.active_tabs[new_handle] = time.time()
            slot.request_count += 1
            logger.debug(
                f"Created tab {new_handle} in browser {slot.browser_id} "
                f"(active_tabs={len(slot.active_tabs)})"
            )
            return new_handle
        except Exception as e:
            logger.error(f"Failed to create new tab: {e}", exc_info=True)
            raise

    async def _release_slot(self, slot: BrowserSlot, tab_handle: str):
        """Mark tab as released and attempt to close it (so it doesn't accumulate)."""
        async with self.lock:
            if tab_handle not in slot.active_tabs:
                return
            # Try to close this specific tab without disturbing others
            try:
                await asyncio.to_thread(slot.browser.switch_to.window, tab_handle)
                await asyncio.to_thread(slot.browser.close)
                # Switch back to the remaining handle so the driver has a valid context
                remaining = await asyncio.to_thread(lambda: slot.browser.window_handles)
                if remaining:
                    await asyncio.to_thread(slot.browser.switch_to.window, remaining[0])
            except Exception as e:
                logger.debug(f"Could not close tab {tab_handle}: {e}")
            finally:
                slot.active_tabs.pop(tab_handle, None)
                logger.debug(
                    f"Released tab in browser {slot.browser_id} "
                    f"(active_tabs={len(slot.active_tabs)})"
                )

    async def _cleanup_loop(self):
        logger.info("Cleanup loop started")
        try:
            while True:
                await asyncio.sleep(60)
                await self._cleanup_idle_resources()
        except asyncio.CancelledError:
            logger.info("Cleanup loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Cleanup loop error: {e}", exc_info=True)

    async def _cleanup_idle_resources(self):
        """Close idle browsers. We no longer walk idle tabs manually — _release_slot
        closes tabs as they finish, so by the time a browser has 0 active_tabs
        and exceeds the idle timeout, it's safe to shut down."""
        current_time = time.time()

        async with self.lock:
            to_remove = [
                s for s in self.browsers
                if not s.active_tabs
                and (current_time - s.created_at) > self.browser_idle_timeout
            ]
            for slot in to_remove:
                try:
                    await self._safe_quit_browser(slot.browser)
                    self.browsers.remove(slot)
                    logger.info(
                        f"Closed idle browser {slot.browser_id} "
                        f"(idle for {int(current_time - slot.created_at)}s)"
                    )
                except Exception as e:
                    logger.error(f"Error closing browser {slot.browser_id}: {e}")

    def get_stats(self) -> PoolStats:
        total_tabs = sum(len(b.active_tabs) for b in self.browsers)
        return PoolStats(
            total_browsers=len(self.browsers),
            active_tabs=total_tabs,
            queued_requests=0,
            total_requests_processed=self.total_requests,
        )

    def describe_browsers(self) -> list:
        """Diagnostic snapshot of the pool."""
        return [
            {
                "id": s.browser_id,
                "headless": s.headless,
                "active_tabs": len(s.active_tabs),
                "request_count": s.request_count,
                "age_seconds": int(time.time() - s.created_at),
            }
            for s in self.browsers
        ]
