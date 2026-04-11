"""
HTTP Server - FastAPI server with browser pool integration.

Handles multiple IDE clients with client tracking and graceful shutdown.
"""
import os
import asyncio
import logging
from typing import Optional, Set
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from mcp_manager.browser_pool import BrowserPool
from mcp_manager.adapters.adapter_factory import get_available_tasks, create_adapter

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
        pid_file: Optional[Path] = None
    ):
        self.host = host
        self.port = port
        self.pid_file = pid_file or Path.home() / ".web-proxy" / "server.pid"

        # Initialize browser pool
        self.browser_pool = BrowserPool(
            max_browsers=max_browsers,
            max_tabs_per_browser=max_tabs_per_browser,
            tab_idle_timeout=tab_idle_timeout,
            browser_idle_timeout=browser_idle_timeout,
            lazy_spawn=lazy_spawn
        )

        # Track connected clients
        self.connected_clients: Set[str] = set()
        self.client_lock = asyncio.Lock()
        self.shutdown_task: Optional[asyncio.Task] = None

        # Create FastAPI app
        self.app = FastAPI(title="MCP Browser Pool Server", version="1.0.0")

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
        """Register FastAPI routes."""

        @self.app.on_event("startup")
        async def startup():
            """Server startup handler."""
            logger.info("Server starting up...")

            # Write PID file
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(os.getpid()))
            logger.info(f"PID file written: {self.pid_file}")

            # Start browser pool
            await self.browser_pool.start()

            logger.info("Server startup complete")

        @self.app.on_event("shutdown")
        async def shutdown():
            """Server shutdown handler."""
            logger.info("Server shutting down...")

            # Stop browser pool
            await self.browser_pool.stop()

            # Remove PID file
            self.pid_file.unlink(missing_ok=True)
            logger.info("PID file removed")

            logger.info("Server shutdown complete")

        @self.app.get("/api/health", response_model=HealthResponse)
        async def health():
            """Health check endpoint."""
            return HealthResponse(
                status="ok",
                timestamp=datetime.utcnow().isoformat()
            )

        @self.app.get("/api/tasks")
        async def get_tasks():
            """Get available tasks."""
            return get_available_tasks()

        @self.app.get("/api/stats", response_model=StatsResponse)
        async def get_stats():
            """Get browser pool statistics."""
            pool_stats = self.browser_pool.get_stats()

            return StatsResponse(
                browsers=pool_stats.total_browsers,
                active_tabs=pool_stats.active_tabs,
                queued_requests=pool_stats.queued_requests,
                total_requests=pool_stats.total_requests_processed,
                connected_clients=len(self.connected_clients)
            )

        @self.app.post("/api/register-client")
        async def register_client(request: ClientRequest):
            """Register a new IDE client."""
            async with self.client_lock:
                self.connected_clients.add(request.client_id)
                logger.info(
                    f"Client {request.client_id} registered. "
                    f"Total clients: {len(self.connected_clients)}"
                )

                # Cancel shutdown task if running
                if self.shutdown_task and not self.shutdown_task.done():
                    self.shutdown_task.cancel()
                    logger.info("Cancelled delayed shutdown (new client connected)")

            return {"status": "registered", "client_id": request.client_id}

        @self.app.post("/api/unregister-client")
        async def unregister_client(request: ClientRequest):
            """Unregister IDE client."""
            async with self.client_lock:
                self.connected_clients.discard(request.client_id)
                logger.info(
                    f"Client {request.client_id} unregistered. "
                    f"Remaining clients: {len(self.connected_clients)}"
                )

                # Schedule shutdown if no clients
                if len(self.connected_clients) == 0:
                    logger.info("No clients connected. Shutting down in 5 minutes...")
                    self.shutdown_task = asyncio.create_task(self._delayed_shutdown(300))

            return {"status": "unregistered", "client_id": request.client_id}

        @self.app.post("/api/query", response_model=QueryResponse)
        async def query(request: QueryRequest):
            """Handle query from IDE client."""
            try:
                logger.info(
                    f"Query request: task={request.task}, model={request.model}, "
                    f"client={request.client_id}"
                )

                # Create adapter
                adapter = create_adapter(request.task)

                # Execute via browser pool
                result = await self.browser_pool.execute_task(
                    adapter,
                    request.prompt,
                    request.model,
                    chrome_path=request.chrome_path,
                    headless=request.headless
                )

                return QueryResponse(result=result)

            except ValueError as e:
                logger.error(f"Invalid request: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(f"Query failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/shutdown")
        async def shutdown_server():
            """Graceful shutdown endpoint."""
            logger.info("Shutdown requested via API")

            # Schedule immediate shutdown
            asyncio.create_task(self._delayed_shutdown(0))

            return {"status": "shutting down"}

    async def _delayed_shutdown(self, delay: int):
        """Delayed shutdown after specified delay.

        Args:
            delay: Delay in seconds before shutdown
        """
        try:
            if delay > 0:
                logger.info(f"Waiting {delay}s before shutdown...")
                await asyncio.sleep(delay)

            # Check if clients reconnected
            async with self.client_lock:
                if len(self.connected_clients) > 0:
                    logger.info(
                        f"Shutdown cancelled - {len(self.connected_clients)} clients connected"
                    )
                    return

            logger.info("Initiating server shutdown...")

            # Trigger shutdown
            import signal
            os.kill(os.getpid(), signal.SIGTERM)

        except asyncio.CancelledError:
            logger.info("Delayed shutdown cancelled")
        except Exception as e:
            logger.error(f"Error during delayed shutdown: {e}", exc_info=True)

    def run(self):
        """Run the HTTP server."""
        import os
        logger.info(f"Starting HTTP server on {self.host}:{self.port}")

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False  # Reduce noise
        )


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    **kwargs
) -> HTTPServer:
    """Create HTTP server instance.

    Args:
        host: Server host
        port: Server port
        **kwargs: Additional arguments for HTTPServer

    Returns:
        HTTPServer instance
    """
    return HTTPServer(host=host, port=port, **kwargs)
