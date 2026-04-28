"""
MCP Server - JSON-RPC stdin/stdout loop with dynamic adapter routing.
Exposes two tools: get_available_tasks and query_premium_model.
"""
import asyncio
import json
import sys
import logging
import argparse
from pathlib import Path

from mcp_manager.browser import get_browser_config, LOG_FILE
from mcp_manager.adapters.adapter_factory import get_available_tasks, create_adapter
from mcp_manager.browser_pool import BrowserPool
from mcp_manager.session_manager import SessionManager
from mcp_manager.utils import sanitize_surrogates

logger = logging.getLogger(__name__)

def setup_logging(log_file=None):
    """Setup logging with file + stderr handlers."""
    if log_file is None:
        log_file = LOG_FILE

    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: Could not create log file at {log_file}: {e}", file=sys.stderr)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )


def log_json(prefix, data):
    """Log JSON data with pretty formatting."""
    try:
        logger.debug(f"{prefix}: {json.dumps(data, indent=2)}")
    except Exception:
        logger.debug(f"{prefix}: {data}")

def _build_tools_list():
    """Build the MCP tools/list response dynamically from config."""
    tasks = get_available_tasks()
    task_names = list(tasks.keys())

    # Collect all unique mode names across tasks
    # OPTIMIZATION: Using dict.fromkeys() for O(N) order-preserving deduplication
    # instead of O(N^2) list membership checks.
    all_mode_names = list(dict.fromkeys(
        m["name"]
        for t in tasks.values()
        for m in t.get("modes", [])
    ))

    task_descriptions = ", ".join(
        f"'{k}': {v['description']}" for k, v in tasks.items()
    )
    mode_descriptions = ", ".join(
        f"'{m['name']}': {m['description']}"
        for m in next(iter(tasks.values()), {}).get("modes", [])
    )

    return [
        {
            "name": "get_available_tasks",
            "description": (
                "Returns a JSON object listing all supported tasks "
                "and their available modes with descriptions."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "query_premium_model",
            "description": (
                "Submits a prompt to a premium LLM via browser automation. "
                "You MUST specify a 'task' and a 'mode'. "
                f"\n\nAvailable tasks: {task_descriptions}."
                f"\n\nAvailable modes: {mode_descriptions}."
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
                        "description": f"Which task to use. One of: {task_names}",
                        "enum": task_names
                    },
                    "mode": {
                        "type": "string",
                        "description": "The chat mode to use.",
                        "enum": all_mode_names
                    }
                },
                "required": ["prompt", "task", "mode"]
            }
        }
    ]

# Global stdout lock to ensure JSON-RPC responses do not interleave when processed concurrently
_stdout_lock = asyncio.Lock()

async def send_response(response):
    """Thread-safe and async-safe stdout writing for JSON-RPC."""
    async with _stdout_lock:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

async def handle_request(req, pool, session_manager):
    """Handle a single JSON-RPC request concurrently."""
    try:
        log_json("REQUEST", req)

        req_id = req.get("id")
        method = req.get("method")

        response = {"jsonrpc": "2.0", "id": req_id}

        # --- INITIALIZE ---
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "mcp-adapter-server", "version": "2.0.0"}
            }

        # --- TOOLS LIST ---
        elif method == "tools/list":
            response["result"] = {"tools": _build_tools_list()}

        # --- RESOURCES & PROMPTS (EMPTY) ---
        elif method in ("resources/list", "resources/templates/list", "prompts/list"):
            key = method.split("/")[0]
            if key == "resources" and "templates" in method:
                response["result"] = {"resourceTemplates": []}
            else:
                response["result"] = {key: []}

        # --- TOOL CALL ---
        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            logger.debug(f"Tool call: {tool_name}")
            log_json("ARGS", arguments)

            if tool_name == "get_available_tasks":
                tasks = get_available_tasks()
                response["result"] = {
                    "content": [{"type": "text", "text": json.dumps(tasks, indent=2)}]
                }

            elif tool_name == "query_premium_model":
                prompt = arguments.get("prompt", "")
                task_name = arguments.get("task", "")
                model = arguments.get("mode", "")
                chrome_path = arguments.get("chrome_path")
                headless = arguments.get("headless")

                logger.info(f"Tool call parameters: task={task_name}, mode={model}, chrome_path={chrome_path}, headless={headless}")

                if not task_name:
                    response["error"] = {
                        "code": -32602,
                        "message": "Missing required parameter: 'task'. Call 'get_available_tasks' to see options."
                    }
                elif not model:
                    response["error"] = {
                        "code": -32602,
                        "message": "Missing required parameter: 'mode'. Call 'get_available_tasks' to see options."
                    }
                else:
                    session = None
                    try:
                        logger.info(f"Creating adapter for task: {task_name}")
                        adapter = create_adapter(task_name)
                        effective_headless = headless if headless is not None else pool.default_headless
                        # Internally: create session -> send message -> end session
                        session = await session_manager.create_session(
                            adapter=adapter,
                            task_name=task_name,
                            model=model,
                            headless=effective_headless,
                        )
                        output = await session_manager.send_message(session.id, prompt)
                        logger.info(f"Query completed. Output length: {len(output)}")
                        response["result"] = {
                            "content": [{"type": "text", "text": sanitize_surrogates(output)}]
                        }
                    except ValueError as e:
                        logger.error(f"Adapter creation failed: {e}")
                        response["error"] = {"code": -32602, "message": str(e)}
                    except Exception as e:
                        logger.error(f"Adapter execution failed: {e}", exc_info=True)
                        response["error"] = {"code": -32603, "message": f"Adapter execution error: {str(e)}"}
                    finally:
                        if session:
                            try:
                                await session_manager.end_session(session.id)
                            except Exception as e:
                                logger.warning(f"Failed to close query session: {e}")

            else:
                response["error"] = {"code": -32601, "message": f"Tool not found: {tool_name}"}

        # --- NOTIFICATIONS (no response needed) ---
        elif req_id is None:
            return

        # --- UNKNOWN ---
        else:
            response["result"] = {}

        log_json("RESPONSE", response)
        await send_response(response)

    except Exception as e:
        logger.error(f"MCP ERROR in handle_request: {e}", exc_info=True)
        if req.get("id"):
            await send_response({
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32603, "message": str(e)}
            })


async def mcp_server():
    """MCP JSON-RPC server loop reading from stdin, processing concurrently."""
    logger.info("MCP server started (adapter architecture)")

    # Share a single pool instance across all requests to massively improve performance
    pool = BrowserPool(max_contexts=5, lazy_spawn=True)
    await pool.start()

    session_manager = SessionManager(pool)
    await session_manager.start()

    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                logger.info("STDIN closed. Shutting down.")
                break

            logger.debug(f"RAW INPUT: {line.strip()}")

            try:
                req = json.loads(line)
                # Dispatch the task concurrently so the server can handle multiple rapid RPC calls
                asyncio.create_task(handle_request(req, pool, session_manager))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON input: {e}")
                await send_response({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                })
    finally:
        await pool.stop()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="MCP Adapter Server - modular LLM browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python main.py
  python main.py --chrome-path "/path/to/chrome"
  python main.py --config ./custom_config.json
        """
    )
    parser.add_argument("--chrome-path", help="Path to Chrome executable")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--no-headless", action="store_true", help="Run Chrome in windowed mode")
    parser.add_argument("--profile-dir", help="Custom Chrome profile directory")
    parser.add_argument("--config", help="Path to adapter config JSON file")
    parser.add_argument("--use-temp-chat", action="store_true", default=True, help="Use temporary chat mode (default: True)")
    parser.add_argument("--no-temp-chat", action="store_true", help="Disable temporary chat mode")
    return parser.parse_args()

def main():
    """Entry point for the MCP server."""
    setup_logging()

    try:
        args = parse_args()

        # Load custom config if provided
        if args.config:
            from mcp_manager.adapters.adapter_factory import load_config
            load_config(args.config)

        # Initialize browser config with CLI overrides
        headless = None
        if args.headless:
            headless = True
        elif args.no_headless:
            headless = False

        profile_dir = Path(args.profile_dir) if args.profile_dir else None
        get_browser_config(args.chrome_path, headless, profile_dir)

        # Determine temp chat setting
        use_temp_chat = True  # Default
        if args.no_temp_chat:
            use_temp_chat = False
        elif args.use_temp_chat:
            use_temp_chat = True

        # Store temp chat setting globally for adapters to access
        from mcp_manager.browser import set_temp_chat_preference
        set_temp_chat_preference(use_temp_chat)

        logger.info("Starting MCP server (adapter architecture)")
        asyncio.run(mcp_server())

    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down.")
        sys.exit(0)
    except FileNotFoundError as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
