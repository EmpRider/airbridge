"""
Session manager — pins a browser slot to a multi-turn chat session.

Each Session owns a BrowserSlot for its entire lifetime, serializes its
own turns via an asyncio.Lock, and is reaped after an idle timeout.

This layer sits on top of BrowserPool and calls the adapter's
start_session() / send_in_session() methods.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class Session:
    id: str
    task_name: str
    model: str
    headless: bool
    client_id: Optional[str]
    slot: any                       # BrowserSlot
    adapter: any                    # GenericAdapter
    state: dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    turns: int = 0
    dead: bool = False
    dead_reason: Optional[str] = None

    def touch(self):
        self.last_used = time.time()

    def info(self) -> dict:
        return {
            "id": self.id,
            "task": self.task_name,
            "model": self.model,
            "headless": self.headless,
            "client_id": self.client_id,
            "turns": self.turns,
            "age_seconds": int(time.time() - self.created_at),
            "idle_seconds": int(time.time() - self.last_used),
            "dead": self.dead,
            "dead_reason": self.dead_reason,
        }


class SessionError(Exception):
    """Raised when a session operation cannot proceed."""


class SessionNotFound(SessionError):
    pass


class SessionDead(SessionError):
    pass


class SessionManager:
    """Owns the lifecycle of multi-turn chat sessions."""

    def __init__(
        self,
        browser_pool,
        idle_timeout: int = 900,        # 15 min
        max_sessions: int = 8,
        reaper_interval: int = 30,
    ):
        self.pool = browser_pool
        self.idle_timeout = idle_timeout
        self.max_sessions = max_sessions
        self.reaper_interval = reaper_interval

        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: Optional[asyncio.Task] = None

    async def start(self):
        self._reaper_task = asyncio.create_task(self._reaper_loop())
        logger.info(
            f"SessionManager started "
            f"(idle_timeout={self.idle_timeout}s, max_sessions={self.max_sessions})"
        )

    async def stop(self):
        logger.info("SessionManager stopping...")
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for s in sessions:
            await self._teardown_session(s, reason="server_shutdown")
        logger.info("SessionManager stopped")

    # ---------- Public API ----------

    async def create_session(
        self,
        adapter,
        task_name: str,
        model: str,
        headless: bool,
        client_id: Optional[str] = None,
    ) -> Session:
        async with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise SessionError(
                    f"Session capacity reached ({self.max_sessions}). "
                    "End an existing session first."
                )

        # Acquire a dedicated slot OUTSIDE our lock — the pool has its own lock
        slot = await self.pool.acquire_dedicated(headless)

        session = Session(
            id=uuid.uuid4().hex,
            task_name=task_name,
            model=model,
            headless=headless,
            client_id=client_id,
            slot=slot,
            adapter=adapter,
        )

        try:
            initial_state = await adapter.start_session(slot.page, model)
            session.state = initial_state or {}
        except Exception as e:
            logger.error(f"start_session failed: {e}", exc_info=True)
            try:
                await self.pool.release_dedicated(slot, close=True)
            except Exception as close_err:
                logger.error(f"Failed releasing slot after start_session error: {close_err}")
            raise SessionError(f"Failed to start session: {e}")

        async with self._lock:
            self._sessions[session.id] = session

        logger.info(
            f"Session {session.id} created "
            f"(task={task_name}, model={model}, client={client_id})"
        )
        return session

    async def send_message(
        self,
        session_id: str,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Send one turn. If `model` is given and differs from the current
        session model, the adapter will switch UI mode for this turn onward."""
        session = self._get_or_404(session_id)
        if session.dead:
            raise SessionDead(f"Session is dead: {session.dead_reason}")

        # Per-session lock — only one turn at a time
        async with session.lock:
            if session.dead:
                raise SessionDead(f"Session is dead: {session.dead_reason}")

            # Validate the underlying page is still alive
            page = session.slot.page
            try:
                if page.is_closed():
                    session.dead = True
                    session.dead_reason = "page_closed"
                    raise SessionDead("Browser page was closed")
            except SessionDead:
                raise
            except Exception as e:
                # For transient network errors, attempt to recover before marking dead
                try:
                    # Try to reload the page to recover from transient issues
                    await page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(1)  # Brief pause for page to stabilize
                    # Check again after reload
                    if page.is_closed():
                        session.dead = True
                        session.dead_reason = f"page_check_failed:{e}"
                        raise SessionDead(str(e))
                    else:
                        logger.info(f"Session {session.id} recovered after page reload")
                        # Continue with the request after recovery
                except Exception as reload_error:
                    session.dead = True
                    session.dead_reason = f"page_check_failed:{e}"
                    raise SessionDead(str(e))

            session.touch()
            try:
                response = await session.adapter.send_in_session(
                    page=page,
                    prompt=prompt,
                    state=session.state,
                    model=model,
                )
            except Exception as e:
                logger.error(f"send_in_session failed: {e}", exc_info=True)
                session.dead = True
                session.dead_reason = f"adapter_error:{e}"
                raise SessionDead(str(e))

            # Keep the top-level session.model in sync with whatever the
            # adapter landed on (for list_sessions / info output).
            new_model = session.state.get("model")
            if new_model:
                session.model = new_model

            session.turns += 1
            session.touch()

            # Adapters can signal auth expiration via a sentinel string
            if isinstance(response, str) and response.startswith("LOGIN_EXPIRED"):
                session.dead = True
                session.dead_reason = "login_expired"

            return response

    async def end_session(self, session_id: str, reason: str = "client_request"):
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFound(session_id)
        await self._teardown_session(session, reason=reason)
        logger.info(f"Session {session_id} ended ({reason})")

    async def end_sessions_for_client(self, client_id: str):
        async with self._lock:
            victims = [s for s in self._sessions.values() if s.client_id == client_id]
            for s in victims:
                self._sessions.pop(s.id, None)
        for s in victims:
            await self._teardown_session(s, reason="client_disconnected")
        if victims:
            logger.info(f"Reaped {len(victims)} session(s) for client {client_id}")

    def list_sessions(self) -> List[dict]:
        return [s.info() for s in self._sessions.values()]

    def get_session_info(self, session_id: str) -> Optional[dict]:
        s = self._sessions.get(session_id)
        return s.info() if s else None

    # ---------- Internals ----------

    def _get_or_404(self, session_id: str) -> Session:
        s = self._sessions.get(session_id)
        if s is None:
            raise SessionNotFound(session_id)
        return s

    async def _teardown_session(self, session: Session, reason: str):
        """Close the session's slot. Waits for the per-session lock so we
        never kill a slot mid-turn."""
        try:
            async with session.lock:
                await self.pool.release_dedicated(session.slot, close=True)
        except Exception as e:
            logger.error(
                f"Teardown failed for {session.id} ({reason}): {e}", exc_info=True
            )

    async def _reaper_loop(self):
        logger.info("Session reaper loop started")
        try:
            while True:
                await asyncio.sleep(self.reaper_interval)
                await self._reap_idle()
        except asyncio.CancelledError:
            logger.info("Session reaper loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Reaper crashed: {e}", exc_info=True)

    async def _reap_idle(self):
        now = time.time()
        async with self._lock:
            victims = [
                s for s in self._sessions.values()
                if s.dead or (now - s.last_used) > self.idle_timeout
            ]
            for s in victims:
                self._sessions.pop(s.id, None)
        for s in victims:
            reason = "dead" if s.dead else "idle_timeout"
            logger.info(f"Reaping session {s.id} ({reason})")
            await self._teardown_session(s, reason=reason)
