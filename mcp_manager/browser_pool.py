"""
Browser Pool Manager — Playwright-based context pool for high concurrency.

Each slot represents an isolated BrowserContext (not a full browser process).
Contexts are natively thread-safe and can execute in parallel without locks.
"""
import asyncio
import time
import logging
import uuid
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BrowserSlot:
    """Represents an isolated browser context with its page."""
    context: any  # Playwright BrowserContext
    page: any  # Playwright Page
    context_id: int
    headless: bool
    created_at: float = field(default_factory=time.time)
    request_count: int = 0
    dedicated: bool = False  # True when pinned to a Session; hidden from rotation


@dataclass
class PoolStats:
    total_contexts: int
    active_contexts: int
    total_requests_processed: int


class BrowserPool:
    """Manages Playwright browser contexts for isolated, parallel execution."""

    def __init__(
        self,
        max_contexts: int = 10,
        context_idle_timeout: int = 1800,
        lazy_spawn: bool = True,
        default_headless: bool = True,
    ):
        self.max_contexts = max_contexts
        self.context_idle_timeout = context_idle_timeout
        self.lazy_spawn = lazy_spawn
        self.default_headless = default_headless

        self.contexts: List[BrowserSlot] = []
        self.lock = asyncio.Lock()
        self.total_requests = 0
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Track pending spawns so we don't exceed max_contexts while unlocked
        self._pending_spawns = 0

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
            for slot in self.contexts:
                # Add timeout to stop hanging the shutdown process
                try:
                    await asyncio.wait_for(slot.context.close(), timeout=3.0)
                except Exception as e:
                    logger.error(f"Error closing context {slot.context_id} during shutdown: {e}")
            self.contexts.clear()

        logger.info("Browser pool stopped")

    async def execute_task(
        self,
        adapter,
        prompt: str,
        model: str,
        headless: Optional[bool] = None,
        **kwargs,
    ):
        """Execute an adapter task on an available context.

        Args:
            adapter: adapter instance with an async .process() method
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
            f"Request {request_id}: acquiring context (headless={effective_headless})..."
        )

        context_slot = await self._get_available_slot(effective_headless)

        try:
            logger.info(
                f"Request {request_id}: executing on context "
                f"{context_slot.context_id} (headless={context_slot.headless})"
            )

            # Playwright is natively async - no need for asyncio.to_thread
            result = await adapter.process(
                prompt,
                model,
                page=context_slot.page,
                **kwargs,
            )

            logger.info(f"Request {request_id}: completed")
            return result

        except Exception as e:
            logger.error(f"Request {request_id}: failed: {e}", exc_info=True)
            raise
        finally:
            await self._release_slot(context_slot)

    async def acquire_dedicated(self, headless: bool) -> BrowserSlot:
        """Pull a fresh slot for exclusive use by a chat session.

        The returned slot is marked .dedicated=True and is invisible to
        _get_available_slot, _try_evict_one, and the idle cleanup loop until
        release_dedicated() is called.
        """
        """Optimized to spawn without holding the main lock."""
        should_spawn = False
        
        async with self.lock:
            total_projected = len(self.contexts) + self._pending_spawns
            if total_projected >= self.max_contexts:
                evicted = await self._try_evict_one_locked(skip_dedicated=True)
                if not evicted:
                    raise RuntimeError(
                        f"Pool at capacity ({self.max_contexts}) with no "
                        "evictable rotation slots; cannot dedicate a slot."
                    )
        
            # Reserve our spot
            self._pending_spawns += 1
            should_spawn = True

        # SPAWN OUTSIDE THE LOCK - Allows concurrent requests to hit existing warm contexts
        try:
            slot = await self._spawn_context(headless)
            slot.dedicated = True
            
            # Re-acquire lock just to append state
            async with self.lock:
                self.contexts.append(slot)
                self._pending_spawns -= 1
            return slot
        except Exception:
            async with self.lock:
                self._pending_spawns -= 1
            raise

    async def release_dedicated(self, slot: BrowserSlot, close: bool = True):
        """Release a session-owned slot.

        If close=True (the default and typical case), the browser context is
        torn down. If close=False, the slot is demoted to a regular rotation
        slot and can be reused by one-shot traffic.
        """
        # State mutation inside lock
        async with self.lock:
            if close and slot in self.contexts:
                self.contexts.remove(slot)
            elif not close:
                slot.dedicated = False
                logger.info(
                    f"Context {slot.context_id} demoted from dedicated to rotation"
                )
                return

        # I/O teardown OUTSIDE lock with timeout
        if close:
            try:
                await asyncio.wait_for(slot.context.close(), timeout=5.0)
                logger.info(f"Closed dedicated context {slot.context_id}")
            except Exception as e:
                logger.error(
                    f"Failed closing dedicated context {slot.context_id}: {e}"
                )

    async def _get_available_slot(self, headless: bool) -> BrowserSlot:
        """Find or create a context slot matching the requested headless mode.

        Dedicated slots (owned by a Session) are invisible to this path.
        """
        # Loop until we secure a slot
        while True:
            should_spawn = False
            
            async with self.lock:
                # 1. Try to find a warm, ready context immediately
                for slot in self.contexts:
                    if slot.dedicated:
                        continue
                    if slot.headless == headless:
                        # Check if context is still open
                        try:
                            # Try to access the context to verify it's still valid
                            _ = slot.context.pages
                            slot.request_count += 1
                            return slot
                        except Exception as e:
                            # Context is closed, remove it from pool
                            logger.warning(f"Context {slot.context_id} is closed, removing from pool: {e}")
                            self.contexts.remove(slot)
                            break
                
                # 2. Check if we have room to spawn
                total_projected = len(self.contexts) + self._pending_spawns
                if total_projected < self.max_contexts:
                    self._pending_spawns += 1
                    should_spawn = True
                else:
                    # 3. Try to evict an idle one to make room
                    non_dedicated = [s for s in self.contexts if not s.dedicated]
                    if non_dedicated and not any(
                        s.headless == headless and not s.dedicated for s in self.contexts
                    ):
                        evicted = await self._try_evict_one_locked(skip_dedicated=True)
                        if evicted:
                            self._pending_spawns += 1
                            should_spawn = True

            # Perform the slow I/O out of the lock
            if should_spawn:
                try:
                    slot = await self._spawn_context(headless)
                    async with self.lock:
                        self.contexts.append(slot)
                        self._pending_spawns -= 1
                        slot.request_count += 1
                    return slot
                except Exception:
                    async with self.lock:
                        self._pending_spawns -= 1
                    raise

            # If we couldn't spawn and no context is ready, wait and retry
            await asyncio.sleep(0.5)

    async def _try_evict_one_locked(self, skip_dedicated: bool = True) -> bool:
        """Evict the oldest idle context. Assumes lock is already held. Only mutates state, defers I/O."""
        candidates = [
            s for s in self.contexts
            if not (skip_dedicated and s.dedicated)
        ]
        if not candidates:
            return False
            
        candidates.sort(key=lambda s: s.created_at)
        victim = candidates[0]
        
        # Remove from state immediately so it's out of rotation
        self.contexts.remove(victim)
        
        # Fire-and-forget the closing task so we don't hold up the lock waiting for Playwright
        asyncio.create_task(self._safe_close_context(victim))
        return True

    async def _safe_close_context(self, slot: BrowserSlot):
        """Helper to cleanly close a context with a strict timeout."""
        try:
            await asyncio.wait_for(slot.context.close(), timeout=5.0)
            logger.info(f"Evicted/Closed context {slot.context_id}")
        except Exception as e:
            logger.error(f"Failed to cleanly close context {slot.context_id}: {e}")

    async def _spawn_context(self, headless: bool) -> BrowserSlot:
        """Spawn a new browser context. Does NOT hold the lock. Performs raw I/O."""
        # Use uuid or timestamp for ID since we aren't under lock
        context_id = id(self) + int(time.time() * 1000) 
        
        try:
            from mcp_manager.browser import get_browser_config

            config = get_browser_config()
            # Use ephemeral context for resource efficiency
            # Session data will be transferred via cookies when needed
            context = await config.create_context(headless_override=headless)
            
            # Get or create a page from the context
            # Ephemeral contexts need a page created
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = await context.new_page()

            slot = BrowserSlot(
                context=context,
                page=page,
                context_id=context_id,
                headless=headless,
            )
            logger.info(f"Context {context_id} spawned (headless={headless}) - ephemeral")
            return slot

        except Exception as e:
            logger.error(f"Failed to spawn context: {e}", exc_info=True)
            raise

    async def _release_slot(self, slot: BrowserSlot):
        """Mark context as released."""
        async with self.lock:
            logger.debug(
                f"Released context {slot.context_id} "
                f"(requests={slot.request_count})"
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
        """Close idle contexts that exceed the idle timeout.

        Dedicated (session-owned) slots are never cleaned up by this loop —
        the SessionManager owns their lifecycle.
        """
        current_time = time.time()
        to_remove = []

        async with self.lock:
            for slot in self.contexts:
                if not slot.dedicated and (current_time - slot.created_at) > self.context_idle_timeout:
                    to_remove.append(slot)
                    
            for slot in to_remove:
                self.contexts.remove(slot)

        # Do the heavy closing outside the lock with timeouts
        for slot in to_remove:
            await self._safe_close_context(slot)

    def get_stats(self) -> PoolStats:
        return PoolStats(
            total_contexts=len(self.contexts),
            active_contexts=len(self.contexts),
            total_requests_processed=self.total_requests,
        )

    def describe_contexts(self) -> list:
        """Diagnostic snapshot of the pool."""
        return [
            {
                "id": s.context_id,
                "headless": s.headless,
                "dedicated": s.dedicated,
                "request_count": s.request_count,
                "age_seconds": int(time.time() - s.created_at),
            }
            for s in self.contexts
        ]
