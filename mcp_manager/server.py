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
    task_descriptions = ", ".join(f"'{k}' ({v['adapter']}): {v['description']}" for k, v in tasks.items())

    return [
        {
            "name": "get_available_tasks",
            "description": "Returns a JSON object listing all supported task types. Call this first to discover which tasks are available before calling query_premium_model.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "query_premium_model",
            "description": f"Submits a prompt to a premium LLM via stealth browser automation. You MUST specify a 'task' parameter to select the target adapter and a 'model' parameter to select the specific chat model. Available tasks: {task_descriptions}. Use 'get_available_tasks' to discover options dynamically.",
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
                        "description": "The specific chat model to use: 'Fast', 'Thinking', or 'Pro'. This determines which Gemini model variant will process your request.",
                        "enum": ["Fast", "Thinking", "Pro"]
                    },
                    "chrome_path": {
                        "type": "string",
                        "description": "Optional: Absolute path to Chrome executable."
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Optional: Run browser invisibly. Set to false if login is needed."
                    }
                },
                "required": ["prompt", "task", "model"]
            }
        }
    ]


async def mcp_server():
    """MCP JSON-RPC server loop reading from stdin, writing to stdout."""
    logger.info("MCP server started (adapter architecture)")

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            logger.info("STDIN closed. Shutting down.")
            break

        logger.debug(f"RAW INPUT: {line.strip()}")

        try:
            req = json.loads(line)
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
                log_json("ARGS", arguments)

                if tool_name == "get_available_tasks":
                    tasks = get_available_tasks()
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
                            "message": "Missing required parameter: 'task'. Call 'get_available_tasks' to see options."
                        }
                    elif not model:
                        response["error"] = {
                            "code": -32602,
                            "message": "Missing required parameter: 'model'. Must be one of: 'Fast', 'Thinking', 'Pro'."
                        }
                    else:
                        try:
                            adapter = create_adapter(task_name)
                            output = await asyncio.to_thread(adapter.process, prompt, model, chrome_path, headless)
                            response["result"] = {
                                "content": [{"type": "text", "text": output}]
                            }
                        except ValueError as e:
                            response["error"] = {"code": -32602, "message": str(e)}

                else:
                    response["error"] = {"code": -32601, "message": f"Tool not found: {tool_name}"}

            # --- NOTIFICATIONS (no response needed) ---
            elif req_id is None:
                continue

            # --- UNKNOWN ---
            else:
                response["result"] = {}

            log_json("RESPONSE", response)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"MCP ERROR: {e}", exc_info=True)
            err = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


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
