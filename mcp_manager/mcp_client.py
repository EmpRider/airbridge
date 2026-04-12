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
    get_server_config,
    DEFAULT_HOST,
    DEFAULT_PORT,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP client that forwards requests to HTTP server.

    Features:
    - Unique client ID per IDE instance
    - Auto-start server if not running (with file lock)
    - Register/unregister with server
    - Forward MCP JSON-RPC to HTTP
    - Detect server/client config mismatch and warn the user
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 600.0,  # 10 minutes for browser automation
        server_kwargs: Optional[dict] = None,
        expected_config: Optional[dict] = None,
    ):
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}"
        self.client_id = str(uuid.uuid4())
        self.http_client = httpx.AsyncClient(timeout=timeout)
        self.initialized = False
        # Server kwargs used when auto-starting (forwarded on fallback too)
        self.server_kwargs = server_kwargs or {}
        # Key-value pairs the client *expects* the server to be running with,
        # used to detect mismatches against /api/config.
        self.expected_config = expected_config or {}

        logger.info(f"MCP client created: {self.client_id}")

    async def initialize(self):
        """Initialize client and ensure server is running.

        Multi-IDE safe:
        1. Check if server running
        2. If not, start it (forwarding CLI kwargs)
        3. Compare server's live config with what we expect — warn on mismatch
        4. Register this client with server
        """
        if self.initialized:
            return

        logger.info("Initializing MCP client...")

        # Ensure server is running (forward kwargs so headless/chrome-path survive)
        if not is_server_running(self.host, self.port):
            logger.info("Server not running, starting it (forwarding CLI args)...")
            start_server_safe(self.host, self.port, **self.server_kwargs)
        else:
            logger.info("Server already running")

        # Config-mismatch detection — helps diagnose "my --no-headless was ignored"
        if self.expected_config:
            live_cfg = get_server_config(self.host, self.port)
            mismatches = []
            for key, want in self.expected_config.items():
                have = live_cfg.get(key)
                if have != want:
                    mismatches.append(f"{key}: server={have!r}, client wants={want!r}")
            if mismatches:
                logger.warning(
                    "Server config mismatch — the already-running server was started "
                    "with different flags than this client's CLI args. "
                    "Per-request overrides (e.g. headless in the query payload) will "
                    "still be honored. Mismatches: %s",
                    "; ".join(mismatches),
                )

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
            # Enforce client's expected config defaults if not explicitly provided in query
            if headless is None and "default_headless" in self.expected_config:
                headless = self.expected_config["default_headless"]

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

    async def start_session(
        self,
        task: str,
        model: str,
        headless: Optional[bool] = None,
    ) -> dict:
        """Open a multi-turn chat session on the server.

        Returns the full session descriptor including session_id. The caller
        (the LLM driving this MCP server) is responsible for remembering the
        session_id and passing it to send_message / end_session.
        """
        if not self.initialized:
            await self.initialize()

        if headless is None and "default_headless" in self.expected_config:
            headless = self.expected_config["default_headless"]

        try:
            response = await self.http_client.post(
                f"{self.server_url}/api/session/start",
                json={
                    "task": task,
                    "model": model,
                    "client_id": self.client_id,
                    "headless": headless,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"start_session HTTP {e.response.status_code}: {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"start_session failed: {e}", exc_info=True)
            raise

    async def send_session_message(
        self,
        session_id: str,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Send one turn inside an existing chat session.

        If `model` is provided, the server will switch the chat mode picker
        (Fast/Thinking/Pro) to that model before sending — letting the caller
        change cognition budget per turn inside the same conversation.
        """
        if not self.initialized:
            await self.initialize()

        payload = {"prompt": prompt}
        if model is not None:
            payload["model"] = model

        try:
            response = await self.http_client.post(
                f"{self.server_url}/api/session/{session_id}/message",
                json=payload,
            )
            response.raise_for_status()
            return response.json()["result"]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"send_session_message HTTP {e.response.status_code}: {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"send_session_message failed: {e}", exc_info=True)
            raise

    async def end_session(self, session_id: str) -> dict:
        """Close a chat session and free its browser slot."""
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.http_client.post(
                f"{self.server_url}/api/session/{session_id}/end",
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"end_session HTTP {e.response.status_code}: {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"end_session failed: {e}", exc_info=True)
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
                            "name": "send_quick_message",
                            "description": (
                                "Submits a SINGLE one-shot prompt to a premium LLM via browser automation. "
                                "Use this for independent questions that do not need to reference any prior "
                                "message. Each call starts a fresh chat — the target model will NOT remember "
                                "anything from previous send_quick_message calls. "
                                "If you need multi-turn conversation where the model should remember prior "
                                "turns (iterative refinement, follow-up questions, step-by-step collaboration), "
                                "use start_chat_session + send_chat_message instead. "
                                f"Available tasks: {task_descriptions}."
                            ),
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
                                    }
                                },
                                "required": ["prompt", "task", "model"]
                            }
                        },
                        {
                            "name": "start_chat_session",
                            "description": (
                                "Opens a multi-turn chat session with a premium LLM. Returns a session_id "
                                "that you MUST remember and pass to every subsequent send_chat_message call "
                                "in the same conversation. The target model will see all previous turns in "
                                "the session as context, so you can ask follow-ups, iterate, or collaborate. "
                                "\n\nUSE THIS when: the user wants a back-and-forth conversation, when you "
                                "need to ask the model to refine a previous answer, when turn N depends on "
                                "the content of turn N-1, or when you are running a multi-step problem-solving "
                                "loop with the model. "
                                "\n\nDO NOT USE for one-off questions — use send_quick_message instead. "
                                "\n\nThe 'model' argument sets the INITIAL mode (Fast/Thinking/Pro). You can "
                                "change mode for individual later turns by passing a different 'model' to "
                                "send_chat_message — the conversation history persists across mode switches, "
                                "so you can use Fast for quick follow-ups and Pro for hard reasoning steps "
                                "inside the same chat. "
                                "\n\nCRITICAL: You MUST call end_chat_session when the conversation is done. "
                                "Each open session holds an exclusive browser slot; leaving them open starves "
                                "capacity. Sessions auto-expire after 15 minutes of idle time, but you should "
                                "end them explicitly as soon as you no longer need the context. "
                                f"\n\nAvailable tasks: {task_descriptions}."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "task": {
                                        "type": "string",
                                        "description": f"Which task/model to use. One of: {task_names}",
                                        "enum": task_names
                                    },
                                    "model": {
                                        "type": "string",
                                        "description": (
                                            "The initial chat model for this session. Can be overridden "
                                            "per-message later via send_chat_message's 'model' argument."
                                        ),
                                        "enum": ["Fast", "Thinking", "Pro"]
                                    }
                                },
                                "required": ["task", "model"]
                            }
                        },
                        {
                            "name": "send_chat_message",
                            "description": (
                                "Sends one message inside an existing chat session and returns the model's "
                                "response. The target LLM sees all previous turns in this session as context. "
                                "\n\nYou MUST pass the session_id that was returned by start_chat_session. "
                                "Using an unknown/expired session_id returns an error — in that case, start a "
                                "new session with start_chat_session. "
                                "\n\nThe optional 'model' argument lets you switch the chat mode "
                                "(Fast/Thinking/Pro) for THIS TURN ONWARD while keeping the conversation "
                                "history intact. Use it to match cognition budget to difficulty: Fast for "
                                "simple follow-ups or clarifications, Thinking for moderate reasoning, Pro "
                                "for the hardest steps. If you omit 'model', the current session mode is "
                                "kept — you do NOT need to pass 'model' every turn. "
                                "\n\nIf this call returns an error mentioning 'session is dead', 'login "
                                "expired', or 'page closed', the session is gone and cannot be recovered — "
                                "you must open a fresh one with start_chat_session."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {
                                        "type": "string",
                                        "description": (
                                            "The session_id returned by a prior start_chat_session call. "
                                            "Must be an active, non-expired session."
                                        )
                                    },
                                    "prompt": {
                                        "type": "string",
                                        "description": "The next message to send in the conversation."
                                    },
                                    "model": {
                                        "type": "string",
                                        "description": (
                                            "Optional per-turn mode override. If set, switches the Gemini "
                                            "mode picker to this model before sending and keeps it for "
                                            "subsequent turns until changed again. Omit to keep the current "
                                            "session mode."
                                        ),
                                        "enum": ["Fast", "Thinking", "Pro"]
                                    }
                                },
                                "required": ["session_id", "prompt"]
                            }
                        },
                        {
                            "name": "end_chat_session",
                            "description": (
                                "Closes a chat session started with start_chat_session and frees its "
                                "browser slot. Call this as soon as you are done with the conversation. "
                                "Safe to call on an already-ended session (returns an error but no harm)."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {
                                        "type": "string",
                                        "description": "The session_id to close."
                                    }
                                },
                                "required": ["session_id"]
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

                elif tool_name == "send_quick_message":
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

                elif tool_name == "start_chat_session":
                    task_name = arguments.get("task", "")
                    model = arguments.get("model", "")
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
                            info = await client.start_session(task_name, model, headless)
                            # The LLM needs the session_id in a form it can read
                            # back out of its own context window.
                            text = json.dumps(info, indent=2)
                            response["result"] = {
                                "content": [{"type": "text", "text": text}]
                            }
                        except httpx.HTTPStatusError as e:
                            code = e.response.status_code
                            response["error"] = {
                                "code": -32603,
                                "message": (
                                    f"start_chat_session failed ({code}): "
                                    f"{e.response.text}"
                                )
                            }
                        except Exception as e:
                            logger.error(f"start_chat_session failed: {e}", exc_info=True)
                            response["error"] = {
                                "code": -32603,
                                "message": f"start_chat_session failed: {str(e)}"
                            }

                elif tool_name == "send_chat_message":
                    session_id = arguments.get("session_id", "")
                    prompt = arguments.get("prompt", "")
                    turn_model = arguments.get("model")  # optional

                    if turn_model is not None and turn_model not in ("Fast", "Thinking", "Pro"):
                        response["error"] = {
                            "code": -32602,
                            "message": (
                                f"Invalid 'model': {turn_model!r}. "
                                "Must be one of: 'Fast', 'Thinking', 'Pro'."
                            ),
                        }
                    elif not session_id:
                        response["error"] = {
                            "code": -32602,
                            "message": (
                                "Missing required parameter: 'session_id'. "
                                "Call start_chat_session first."
                            )
                        }
                    elif not prompt:
                        response["error"] = {
                            "code": -32602,
                            "message": "Missing required parameter: 'prompt'"
                        }
                    else:
                        try:
                            text = await client.send_session_message(
                                session_id, prompt, model=turn_model
                            )
                            response["result"] = {
                                "content": [{"type": "text", "text": text}]
                            }
                        except httpx.HTTPStatusError as e:
                            code = e.response.status_code
                            # Give the LLM a clear, actionable message so it
                            # knows to start a new session on 404/410.
                            if code == 404:
                                msg = (
                                    f"Session '{session_id}' not found. It may have "
                                    "expired or never existed. Call start_chat_session "
                                    "to open a new one."
                                )
                            elif code == 410:
                                msg = (
                                    f"Session '{session_id}' is dead ({e.response.text}). "
                                    "Call start_chat_session to open a new one."
                                )
                            else:
                                msg = (
                                    f"send_chat_message failed ({code}): "
                                    f"{e.response.text}"
                                )
                            response["error"] = {"code": -32603, "message": msg}
                        except Exception as e:
                            logger.error(f"send_chat_message failed: {e}", exc_info=True)
                            response["error"] = {
                                "code": -32603,
                                "message": f"send_chat_message failed: {str(e)}"
                            }

                elif tool_name == "end_chat_session":
                    session_id = arguments.get("session_id", "")

                    if not session_id:
                        response["error"] = {
                            "code": -32602,
                            "message": "Missing required parameter: 'session_id'"
                        }
                    else:
                        try:
                            info = await client.end_session(session_id)
                            response["result"] = {
                                "content": [
                                    {"type": "text", "text": json.dumps(info)}
                                ]
                            }
                        except httpx.HTTPStatusError as e:
                            code = e.response.status_code
                            if code == 404:
                                # Idempotent-ish: already gone is fine
                                response["result"] = {
                                    "content": [{
                                        "type": "text",
                                        "text": json.dumps({
                                            "status": "already_ended",
                                            "session_id": session_id,
                                        }),
                                    }]
                                }
                            else:
                                response["error"] = {
                                    "code": -32603,
                                    "message": (
                                        f"end_chat_session failed ({code}): "
                                        f"{e.response.text}"
                                    ),
                                }
                        except Exception as e:
                            logger.error(f"end_chat_session failed: {e}", exc_info=True)
                            response["error"] = {
                                "code": -32603,
                                "message": f"end_chat_session failed: {str(e)}"
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
