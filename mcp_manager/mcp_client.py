"""
MCP Client - Thin client that forwards MCP JSON-RPC to HTTP server.

Handles multi-IDE coordination with auto-start and client registration.
"""
import asyncio
import json
import sys
import uuid
import atexit
import logging
from typing import Optional

import httpx

from mcp_manager.server_manager import (
    is_server_running,
    start_server_safe,
    DEFAULT_HOST,
    DEFAULT_PORT
)

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP client that forwards requests to HTTP server.

    Features:
    - Unique client ID per IDE instance
    - Auto-start server if not running (with file lock)
    - Register/unregister with server
    - Forward MCP JSON-RPC to HTTP
    - Maintain backward compatibility
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 600.0  # 10 minutes for browser automation
    ):
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}"
        self.client_id = str(uuid.uuid4())
        self.http_client = httpx.AsyncClient(timeout=timeout)
        self.initialized = False

        logger.info(f"MCP client created: {self.client_id}")

    async def initialize(self):
        """Initialize client and ensure server is running.

        Multi-IDE safe:
        1. Check if server running
        2. If not, start it (with file lock)
        3. Register this client with server
        """
        if self.initialized:
            return

        logger.info("Initializing MCP client...")

        # Ensure server is running
        if not is_server_running(self.host, self.port):
            logger.info("Server not running, starting it...")
            start_server_safe(self.host, self.port)
        else:
            logger.info("Server already running")

        # Register this client
        try:
            response = await self.http_client.post(
                f"{self.server_url}/api/register-client",
                json={"client_id": self.client_id}
            )
            response.raise_for_status()
            logger.info(f"Client {self.client_id} registered with server")
        except Exception as e:
            logger.error(f"Failed to register client: {e}")
            raise

        # Register cleanup on exit
        atexit.register(self.cleanup)

        self.initialized = True
        logger.info("MCP client initialized")

    async def query(
        self,
        prompt: str,
        task: str,
        model: str,
        chrome_path: Optional[str] = None,
        headless: Optional[bool] = None
    ) -> str:
        """Send query to server.

        Returns immediately if slot available.
        Waits in queue if all 10 slots busy.

        Args:
            prompt: The prompt to send
            task: The task name
            model: The model to use
            chrome_path: Optional Chrome path
            headless: Optional headless setting

        Returns:
            The response from the server
        """
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.http_client.post(
                f"{self.server_url}/api/query",
                json={
                    "prompt": prompt,
                    "task": task,
                    "model": model,
                    "client_id": self.client_id,
                    "chrome_path": chrome_path,
                    "headless": headless
                }
            )
            response.raise_for_status()

            result = response.json()
            return result["result"]

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            raise

    async def get_tasks(self) -> dict:
        """Get available tasks from server.

        Returns:
            Dictionary of available tasks
        """
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.http_client.get(f"{self.server_url}/api/tasks")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get tasks: {e}")
            raise

    async def get_stats(self) -> dict:
        """Get server statistics.

        Returns:
            Dictionary with server stats
        """
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.http_client.get(f"{self.server_url}/api/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            raise

    def cleanup(self):
        """Unregister client on exit."""
        if not self.initialized:
            return

        try:
            logger.info(f"Unregistering client {self.client_id}...")

            # Use synchronous httpx for cleanup
            with httpx.Client(timeout=5.0) as client:
                response = client.post(
                    f"{self.server_url}/api/unregister-client",
                    json={"client_id": self.client_id}
                )
                response.raise_for_status()

            logger.info("Client unregistered successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()


async def mcp_client_loop(client: MCPClient):
    """MCP JSON-RPC stdin/stdout loop.

    Reads MCP requests from stdin, forwards to HTTP server, returns responses.
    """
    logger.info("MCP client loop started")

    while True:
        try:
            # Read line from stdin
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                logger.info("STDIN closed. Shutting down.")
                break

            logger.debug(f"RAW INPUT: {line.strip()}")

            # Parse JSON-RPC request
            req = json.loads(line)
            logger.debug(f"REQUEST: {json.dumps(req, indent=2)}")

            req_id = req.get("id")
            method = req.get("method")

            response = {"jsonrpc": "2.0", "id": req_id}

            # --- INITIALIZE ---
            if method == "initialize":
                await client.initialize()
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "serverInfo": {"name": "mcp-client", "version": "2.0.0"}
                }

            # --- TOOLS LIST ---
            elif method == "tools/list":
                tasks = await client.get_tasks()
                task_names = list(tasks.keys())
                task_descriptions = ", ".join(
                    f"'{k}' ({v['adapter']}): {v['description']}"
                    for k, v in tasks.items()
                )

                response["result"] = {
                    "tools": [
                        {
                            "name": "get_available_tasks",
                            "description": "Returns a JSON object listing all supported task types.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "required": []
                            }
                        },
                        {
                            "name": "query_premium_model",
                            "description": f"Submits a prompt to a premium LLM via browser automation. Available tasks: {task_descriptions}.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "The exact text prompt to send to the LLM."
                                    },
                                    "task": {
                                        "type": "string",
                                        "description": f"Which task/model to use. One of: {task_names}",
                                        "enum": task_names
                                    },
                                    "model": {
                                        "type": "string",
                                        "description": "The specific chat model to use.",
                                        "enum": ["Fast", "Thinking", "Pro"]
                                    },
                                    "chrome_path": {
                                        "type": "string",
                                        "description": "Optional: Absolute path to Chrome executable."
                                    },
                                    "headless": {
                                        "type": "boolean",
                                        "description": "Optional: Run browser invisibly."
                                    }
                                },
                                "required": ["prompt", "task", "model"]
                            }
                        }
                    ]
                }

            # --- RESOURCES (EMPTY) ---
            elif method == "resources/list":
                response["result"] = {"resources": []}
            elif method == "resources/templates/list":
                response["result"] = {"resourceTemplates": []}

            # --- PROMPTS (EMPTY) ---
            elif method == "prompts/list":
                response["result"] = {"prompts": []}

            # --- TOOL CALL ---
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                logger.debug(f"Tool call: {tool_name}")

                if tool_name == "get_available_tasks":
                    tasks = await client.get_tasks()
                    response["result"] = {
                        "content": [{"type": "text", "text": json.dumps(tasks, indent=2)}]
                    }

                elif tool_name == "query_premium_model":
                    prompt = arguments.get("prompt", "")
                    task_name = arguments.get("task", "")
                    model = arguments.get("model", "")
                    chrome_path = arguments.get("chrome_path")
                    headless = arguments.get("headless")

                    if not task_name:
                        response["error"] = {
                            "code": -32602,
                            "message": "Missing required parameter: 'task'"
                        }
                    elif not model:
                        response["error"] = {
                            "code": -32602,
                            "message": "Missing required parameter: 'model'"
                        }
                    else:
                        try:
                            result = await client.query(
                                prompt, task_name, model, chrome_path, headless
                            )
                            response["result"] = {
                                "content": [{"type": "text", "text": result}]
                            }
                        except Exception as e:
                            logger.error(f"Query failed: {e}", exc_info=True)
                            response["error"] = {
                                "code": -32603,
                                "message": f"Query failed: {str(e)}"
                            }

                else:
                    response["error"] = {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }

            # --- NOTIFICATIONS (no response needed) ---
            elif req_id is None:
                continue

            # --- UNKNOWN ---
            else:
                response["result"] = {}

            # Write response
            logger.debug(f"RESPONSE: {json.dumps(response, indent=2)}")
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"MCP client error: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()

    # Cleanup
    await client.close()
    logger.info("MCP client loop ended")
