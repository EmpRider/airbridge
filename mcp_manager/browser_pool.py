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

        logger.info(
            f"Browser pool initialized: max_contexts={max_contexts}, "
            f"lazy_spawn={lazy_spawn}, default_headless={default_headless}"
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
            for slot in self.contexts:
                try:
                    await slot.context.close()
                    logger.info(f"Closed context {slot.context_id}")
                except Exception as e:
                    logger.error(f"Error closing context {slot.context_id}: {e}")
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

    async def _get_available_slot(self, headless: bool) -> BrowserSlot:
        """Find or create a context slot matching the requested headless mode."""
        async with self.lock:
            # Look for an existing matching-mode context that's still valid
            for slot in self.contexts:
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

            # Need a new context — check capacity
            if len(self.contexts) < self.max_contexts:
                slot = await self._spawn_context(headless)
                return slot

            # At capacity. Try evicting an idle mismatched context
            if not any(s.headless == headless for s in self.contexts):
                evicted = await self._try_evict_one()
                if evicted:
                    slot = await self._spawn_context(headless)
                    return slot

        # Pool is saturated; wait for a slot
        logger.info(
            f"All {self.max_contexts} contexts busy, "
            f"waiting for headless={headless} slot..."
        )
        while True:
            await asyncio.sleep(0.5)
            async with self.lock:
                for slot in self.contexts:
                    if slot.headless == headless:
                        slot.request_count += 1
                        logger.info("Context became available")
                        return slot

    async def _try_evict_one(self) -> bool:
        """Evict the oldest idle context. Caller holds self.lock."""
        if not self.contexts:
            return False
        # Oldest first
        self.contexts.sort(key=lambda s: s.created_at)
        victim = self.contexts[0]
        try:
            await victim.context.close()
            self.contexts.remove(victim)
            logger.info(
                f"Evicted idle context {victim.context_id} (headless={victim.headless})"
            )
            return True
        except Exception as e:
            logger.error(f"Eviction failed: {e}")
            return False

    async def _spawn_context(self, headless: bool) -> BrowserSlot:
        """Spawn a new browser context. Caller holds self.lock."""
        context_id = (max((s.context_id for s in self.contexts), default=0) or 0) + 1
        logger.info(f"Spawning context {context_id} (headless={headless})...")

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
            self.contexts.append(slot)
            logger.info(f"Context {context_id} spawned (headless={headless}) - ephemeral")
            return slot

        except Exception as e:
            logger.error(f"Failed to spawn context {context_id}: {e}", exc_info=True)
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
        """Close idle contexts that exceed the idle timeout."""
        current_time = time.time()

        async with self.lock:
            to_remove = [
                s for s in self.contexts
                if (current_time - s.created_at) > self.context_idle_timeout
            ]
            for slot in to_remove:
                try:
                    await slot.context.close()
                    self.contexts.remove(slot)
                    logger.info(
                        f"Closed idle context {slot.context_id} "
                        f"(idle for {int(current_time - slot.created_at)}s)"
                    )
                except Exception as e:
                    logger.error(f"Error closing context {slot.context_id}: {e}")

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
                "request_count": s.request_count,
                "age_seconds": int(time.time() - s.created_at),
            }
            for s in self.contexts
        ]
