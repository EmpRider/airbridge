"""
HTTP Server — FastAPI server with browser pool integration.

Handles multiple IDE clients with client tracking, graceful shutdown,
and a /api/config endpoint so clients can detect settings mismatches.
"""
import os
import sys
import asyncio
import logging
from typing import Optional, Set, Any, Dict
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from mcp_manager.browser_pool import BrowserPool
from mcp_manager.adapters.adapter_factory import get_available_tasks, create_adapter
from mcp_manager.session_manager import (
    SessionManager,
    SessionError,
    SessionNotFound,
    SessionDead,
)

logger = logging.getLogger(__name__)


# Request/Response models
class QueryRequest(BaseModel):
    prompt: str
    task: str
    model: str
    client_id: Optional[str] = None
    chrome_path: Optional[str] = None
    headless: Optional[bool] = None


class QueryResponse(BaseModel):
    result: str


class ClientRequest(BaseModel):
    client_id: str


class HealthResponse(BaseModel):
    status: str
    timestamp: str


class StatsResponse(BaseModel):
    browsers: int
    active_tabs: int
    queued_requests: int
    total_requests: int
    connected_clients: int


class StartSessionRequest(BaseModel):
    task: str
    model: str
    client_id: Optional[str] = None
    headless: Optional[bool] = None


class SessionMessageRequest(BaseModel):
    prompt: str
    model: Optional[str] = None  # optional per-turn override; None keeps current


class HTTPServer:
    """HTTP server with browser pool and client tracking."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        max_browsers: int = 2,
        max_tabs_per_browser: int = 5,
        tab_idle_timeout: int = 300,
        browser_idle_timeout: int = 1800,
        lazy_spawn: bool = True,
        pid_file: Optional[Path] = None,
        # Config snapshot so /api/config can surface the real state
        default_headless: bool = True,
        use_temp_chat: bool = True,
        chrome_path: Optional[str] = None,
        profile_dir: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.pid_file = pid_file or Path.home() / ".web-proxy" / "server.pid"

        # Snapshot the server config so clients can inspect it
        self.config_snapshot: Dict[str, Any] = {
            "host": host,
            "port": port,
            "max_browsers": max_browsers,
            "max_tabs_per_browser": max_tabs_per_browser,
            "tab_idle_timeout": tab_idle_timeout,
            "browser_idle_timeout": browser_idle_timeout,
            "lazy_spawn": lazy_spawn,
            "default_headless": default_headless,
            "use_temp_chat": use_temp_chat,
            "chrome_path": chrome_path,
            "profile_dir": profile_dir,
            "pid": os.getpid(),
            "started_at": datetime.utcnow().isoformat(),
        }

        # Initialize browser pool
        self.browser_pool = BrowserPool(
            max_contexts=max_browsers,  # Renamed from max_browsers
            context_idle_timeout=browser_idle_timeout,  # Renamed from browser_idle_timeout
            lazy_spawn=lazy_spawn,
            default_headless=default_headless,
        )

        # Multi-turn chat session manager (sits on top of the pool)
        self.session_manager = SessionManager(
            browser_pool=self.browser_pool,
            idle_timeout=900,           # 15 minutes
            max_sessions=max_browsers,  # never out-compete one-shot capacity
        )

        # Track connected clients
        self.connected_clients: Set[str] = set()
        self.client_lock = asyncio.Lock()
        self.shutdown_task: Optional[asyncio.Task] = None
        self.shutdown_committed: bool = False

        # Create FastAPI app
        self.app = FastAPI(title="MCP Browser Pool Server", version="1.1.0")

        # Add CORS middleware (local only)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost", "http://127.0.0.1"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes()

        logger.info(f"HTTP server initialized on {host}:{port}")

    def _register_routes(self):
        @self.app.on_event("startup")
        async def startup():
            logger.info("Server starting up...")
            try:
                self.pid_file.parent.mkdir(parents=True, exist_ok=True)
                self.pid_file.write_text(str(os.getpid()))
                logger.info(f"PID file written: {self.pid_file}")
            except Exception as e:
                # Write error to stderr so start_server_safe sees it
                print(f"FATAL: Could not write PID file: {e}", file=sys.stderr, flush=True)
                raise

            await self.browser_pool.start()
            await self.session_manager.start()
            logger.info("Server startup complete")

        @self.app.on_event("shutdown")
        async def shutdown():
            logger.info("Server shutting down...")
            await self.session_manager.stop()
            await self.browser_pool.stop()
            try:
                self.pid_file.unlink(missing_ok=True)
                logger.info("PID file removed")
            except Exception as e:
                logger.warning(f"Could not remove PID file: {e}")
            logger.info("Server shutdown complete")

        @self.app.get("/api/health", response_model=HealthResponse)
        async def health():
            return HealthResponse(
                status="ok",
                timestamp=datetime.utcnow().isoformat(),
            )

        @self.app.get("/api/config")
        async def get_config():
            """Return the server's active config so clients can detect mismatches."""
            snapshot = dict(self.config_snapshot)
            snapshot["browsers"] = self.browser_pool.describe_browsers()
            snapshot["connected_clients"] = len(self.connected_clients)
            return snapshot

        @self.app.get("/api/tasks")
        async def get_tasks():
            return get_available_tasks()

        @self.app.get("/api/stats", response_model=StatsResponse)
        async def get_stats():
            pool_stats = self.browser_pool.get_stats()
            return StatsResponse(
                browsers=pool_stats.total_browsers,
                active_tabs=pool_stats.active_tabs,
                queued_requests=pool_stats.queued_requests,
                total_requests=pool_stats.total_requests_processed,
                connected_clients=len(self.connected_clients),
            )

        @self.app.post("/api/register-client")
        async def register_client(request: ClientRequest):
            async with self.client_lock:
                if self.shutdown_committed:
                    logger.info(f"Client {request.client_id} tried to register during committed shutdown")
                    raise HTTPException(status_code=503, detail="Server is shutting down")

                self.connected_clients.add(request.client_id)
                logger.info(
                    f"Client {request.client_id} registered. "
                    f"Total clients: {len(self.connected_clients)}"
                )
                if self.shutdown_task and not self.shutdown_task.done():
                    self.shutdown_task.cancel()
                    logger.info("Cancelled delayed shutdown (new client connected)")
            return {"status": "registered", "client_id": request.client_id}

        @self.app.post("/api/unregister-client")
        async def unregister_client(request: ClientRequest):
            async with self.client_lock:
                self.connected_clients.discard(request.client_id)
                logger.info(
                    f"Client {request.client_id} unregistered. "
                    f"Remaining clients: {len(self.connected_clients)}"
                )
                if len(self.connected_clients) == 0:
                    logger.info("No clients connected. Shutting down in 5 minutes...")
                    self.shutdown_task = asyncio.create_task(self._delayed_shutdown(300))

            # Reap any sessions that belonged to this client — outside client_lock
            try:
                await self.session_manager.end_sessions_for_client(request.client_id)
            except Exception as e:
                logger.warning(
                    f"Failed to reap sessions for {request.client_id}: {e}"
                )
            return {"status": "unregistered", "client_id": request.client_id}

        @self.app.post("/api/query", response_model=QueryResponse)
        async def query(request: QueryRequest):
            try:
                logger.info(
                    f"Query: task={request.task}, model={request.model}, "
                    f"headless={request.headless}, client={request.client_id}"
                )
                adapter = create_adapter(request.task)
                result = await self.browser_pool.execute_task(
                    adapter,
                    request.prompt,
                    request.model,
                    headless=request.headless,  # honored per-request now
                )
                return QueryResponse(result=result)
            except ValueError as e:
                logger.error(f"Invalid request: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"Query failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        # ---------------- Chat session endpoints ----------------

        @self.app.post("/api/session/start")
        async def session_start(req: StartSessionRequest):
            try:
                adapter = create_adapter(req.task)
                effective_headless = (
                    self.config_snapshot["default_headless"]
                    if req.headless is None
                    else bool(req.headless)
                )
                session = await self.session_manager.create_session(
                    adapter=adapter,
                    task_name=req.task,
                    model=req.model,
                    headless=effective_headless,
                    client_id=req.client_id,
                )
                return {"session_id": session.id, **session.info()}
            except SessionError as e:
                logger.warning(f"Session start rejected: {e}")
                raise HTTPException(status_code=429, detail=str(e))
            except ValueError as e:
                logger.error(f"Invalid session start: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"Session start failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/session/{session_id}/message")
        async def session_message(session_id: str, req: SessionMessageRequest):
            try:
                text = await self.session_manager.send_message(
                    session_id, req.prompt, model=req.model
                )
                return {"result": text, "session_id": session_id}
            except SessionNotFound:
                raise HTTPException(status_code=404, detail="session not found")
            except SessionDead as e:
                # 410 Gone — client should create a new session
                raise HTTPException(status_code=410, detail=str(e))
            except Exception as e:
                logger.error(f"Session message failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/session/{session_id}/end")
        async def session_end(session_id: str):
            try:
                await self.session_manager.end_session(session_id)
                return {"status": "ended", "session_id": session_id}
            except SessionNotFound:
                raise HTTPException(status_code=404, detail="session not found")
            except Exception as e:
                logger.error(f"Session end failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions")
        async def sessions_list():
            return {"sessions": self.session_manager.list_sessions()}

        @self.app.post("/api/shutdown")
        async def shutdown_server():
            logger.info("Shutdown requested via API")
            asyncio.create_task(self._delayed_shutdown(0))
            return {"status": "shutting down"}

    async def _delayed_shutdown(self, delay: int):
        try:
            if delay > 0:
                logger.info(f"Waiting {delay}s before shutdown...")
                await asyncio.sleep(delay)

            async with self.client_lock:
                if len(self.connected_clients) > 0:
                    logger.info(
                        f"Shutdown cancelled — {len(self.connected_clients)} clients connected"
                    )
                    return
                self.shutdown_committed = True

            logger.info("Initiating server shutdown...")
            import signal
            os.kill(os.getpid(), signal.SIGTERM)
        except asyncio.CancelledError:
            logger.info("Delayed shutdown cancelled")
        except Exception as e:
            logger.error(f"Error during delayed shutdown: {e}", exc_info=True)

    def run(self):
        logger.info(f"Starting HTTP server on {self.host}:{self.port}")
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,
        )


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    **kwargs,
) -> HTTPServer:
    return HTTPServer(host=host, port=port, **kwargs)
