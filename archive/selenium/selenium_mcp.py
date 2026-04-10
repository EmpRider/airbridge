import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

# ---------------- CONFIG ----------------
GEMINI_URL = "https://gemini.google.com/app"

# Timeout configuration (1 hour = 3600 seconds)
SCRIPT_TIMEOUT = 3600  # Max time for JavaScript execution
CONNECTION_TIMEOUT = 3600  # Max time for HTTP connection reads

BASE_DIR = Path.home() / "web-proxy"
USER_DATA_DIR = BASE_DIR / "edge-debug-profile"
LOG_FILE = BASE_DIR / "mcp.log"

BASE_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.DEBUG,  # 🔥 FULL DEBUG
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),  # MCP safe
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

def log_json(prefix, data):
    try:
        logging.debug(f"{prefix}: {json.dumps(data, indent=2)}")
    except:
        logging.debug(f"{prefix}: {data}")

# ---------------- DRIVER PATH ----------------
def get_webdriver_path():
    cache = Path.home() / ".cache/selenium"

    for p in cache.rglob("msedgedriver.exe"):
        logging.debug(f"Found WebDriver: {p}")
        return str(p)

    logging.info("WebDriver not found. Downloading via Selenium Manager...")
    tmp = webdriver.Edge()
    tmp.quit()

    for p in cache.rglob("msedgedriver.exe"):
        logging.debug(f"Downloaded WebDriver: {p}")
        return str(p)

    raise Exception("WebDriver not found")

# ---------------- GEMINI TOOL ----------------
def ask_gemini(prompt: str) -> str:
    driver = None

    try:
        logging.info("=== NEW GEMINI REQUEST ===")
        logging.info(f"Prompt: {prompt}")

        options = Options()

        # 🔥 Persist login
        options.add_argument(f"--user-data-dir={USER_DATA_DIR}")

        # 🔥 Force separate instance
        options.add_argument("--new-window")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        # stability
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")

        service = Service(get_webdriver_path())

        logging.debug("Launching Edge WebDriver...")
        driver = webdriver.Edge(service=service, options=options)
        
        # Set script timeout to 1 hour for long Gemini responses
        driver.set_script_timeout(SCRIPT_TIMEOUT)
        
        # Configure urllib3 connection timeout (fixes ReadTimeoutError)
        driver.command_executor._client_config.timeout = CONNECTION_TIMEOUT

        logging.debug(f"Opening URL: {GEMINI_URL}")
        driver.get(GEMINI_URL)

        time.sleep(5)

        logging.debug("Executing Gemini script...")

        # Properly escape the prompt for JavaScript
        escaped_prompt = json.dumps(prompt)

        result = driver.execute_async_script(f"""
            const callback = arguments[0];
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));

            try {{
                let finished = false;
                let lastLength = 0;
                let stableCount = 0;

                let interval = setInterval(() => {{
                    try {{
                        const msgs = document.querySelectorAll('message-content');
                        if (msgs.length > 0) {{
                            const last = msgs[msgs.length - 1].innerText;
                            const currentLength = last ? last.length : 0;

                            // Check if response has stopped growing (stable for 3 checks)
                            if (currentLength > 20) {{
                                if (currentLength === lastLength) {{
                                    stableCount++;
                                    if (stableCount >= 3) {{
                                        finished = true;
                                        clearInterval(interval);
                                        callback(last);
                                    }}
                                }} else {{
                                    stableCount = 0;
                                    lastLength = currentLength;
                                }}
                            }}
                        }}
                    }} catch (e) {{
                        finished = true;
                        clearInterval(interval);
                        callback("JS ERROR: " + e.message);
                    }}
                }}, 1000);

                async function run() {{
                    const input = document.querySelector('[data-placeholder="Ask Gemini"]');

                    if (!input) {{
                        callback("ERROR: input not found");
                        return;
                    }}

                    const promptText = {escaped_prompt};
                    input.focus();
                    document.execCommand('insertText', false, promptText);

                    await sleep(500);

                    input.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter',
                        bubbles: true
                    }}));
                }}

                run();

            }} catch (err) {{
                callback("FATAL: " + err.message);
            }}
        """)

        logging.info("Response received from Gemini")
        return result

    except Exception as e:
        logging.error(f"ask_gemini FAILED: {e}", exc_info=True)
        return f"ERROR: {str(e)}"

    finally:
        if driver:
            try:
                logging.debug("Closing WebDriver...")
                driver.quit()
            except Exception as e:
                logging.error(f"Error closing driver: {e}")

        logging.info("=== REQUEST COMPLETE ===")

# ---------------- MCP SERVER ----------------
async def mcp_server():
    logging.info("MCP server started")

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)

        if not line:
            logging.info("STDIN closed. Shutting down.")
            break

        logging.debug(f"RAW INPUT: {line.strip()}")

        try:
            req = json.loads(line)
            log_json("REQUEST", req)

            req_id = req.get("id")
            method = req.get("method")

            response = {
                "jsonrpc": "2.0",
                "id": req_id
            }

            # ---------------- INITIALIZE ----------------
            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": "gemini-browser-bridge",
                        "version": "5.1.0"
                    }
                }

            # ---------------- TOOLS ----------------
            elif method == "tools/list":
                response["result"] = {
                    "tools": [
                        {
                            "name": "ask_gemini",
                            "description": "Send a prompt to Gemini via Edge browser automation",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "Prompt to send to Gemini"
                                    }
                                },
                                "required": ["prompt"]
                            }
                        }
                    ]
                }

            # ---------------- RESOURCES (EMPTY) ----------------
            elif method == "resources/list":
                response["result"] = {
                    "resources": []
                }

            elif method == "resources/templates/list":
                response["result"] = {
                    "resourceTemplates": []
                }

            # ---------------- PROMPTS (EMPTY) ----------------
            elif method == "prompts/list":
                response["result"] = {
                    "prompts": []
                }

            # ---------------- TOOL CALL ----------------
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                logging.debug(f"Tool call: {tool_name}")
                log_json("ARGS", arguments)

                if tool_name == "ask_gemini":
                    prompt = arguments.get("prompt", "")
                    output = ask_gemini(prompt)

                    response["result"] = {
                        "content": [
                            {
                                "type": "text",
                                "text": output
                            }
                        ]
                    }
                else:
                    response["error"] = {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }

            # ---------------- NOTIFICATIONS ----------------
            elif req_id is None:
                continue

            # ---------------- UNKNOWN ----------------
            else:
                # 🔥 DO NOT ERROR → return empty result
                response["result"] = {}

            log_json("RESPONSE", response)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logging.error(f"MCP ERROR: {e}", exc_info=True)

            err = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    try:
        asyncio.run(mcp_server())
    except Exception as e:
        logging.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}))
        sys.stdout.flush()