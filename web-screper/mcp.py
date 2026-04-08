import asyncio
import json
import logging
import socket
import subprocess
import sys
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

# ---------------- CONFIG ----------------
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT = 9222
USER_DATA_DIR = r"D:\edge-debug-profile"
GEMINI_URL = "https://gemini.google.com/app"

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),  # MCP safe
        logging.FileHandler("D:\web-chat\web-screper\mcp.log", encoding="utf-8")  # 👈 ADD THIS
    ]
)

driver = None


# ---------------- WAIT FOR DEBUG PORT ----------------
def wait_for_debug_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except:
            time.sleep(0.5)
    return False


# ---------------- INIT BROWSER ----------------
def init_browser():
    global driver

    if driver:
        logging.info("Browser already initialized.")
        return

    try:
        logging.info("Launching Edge with Gemini...")

        subprocess.Popen([
            EDGE_PATH,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={USER_DATA_DIR}",
            GEMINI_URL
        ])

        if not wait_for_debug_port(DEBUG_PORT):
            raise Exception("Edge debug port not ready")

        logging.info("Connecting Selenium to Edge...")

        # 1. Setup Options for Debugging
        edge_options = Options()
        edge_options.add_experimental_option(
            "debuggerAddress", f"127.0.0.1:{DEBUG_PORT}"
        )

        # 2. Setup the Service object (Correct way for Selenium 4)
        edge_driver_path = r"D:\web-chat\web-screper\msedgedriver.exe"
        service = Service(executable_path=edge_driver_path)

        # 3. Initialize driver with the service object
        # NOTE: Removed executable_path from here
        driver = webdriver.Edge(service=service, options=edge_options)

        # Attach to first tab
        handles = driver.window_handles
        if not handles:
            raise Exception("No browser tabs found")

        driver.switch_to.window(handles[0])

        logging.info(f"Connected to: {driver.current_url}")
        time.sleep(5)

    except Exception as e:
        logging.error(f"Browser init failed: {e}")
        driver = None
        raise


# ---------------- GEMINI TOOL ----------------
def ask_gemini(prompt: str) -> str:
    global driver

    try:
        if not driver:
            init_browser()

        logging.info(f"Prompt: {prompt}")

        result = driver.execute_async_script(f"""
            const callback = arguments[0];

            const sleep = (ms) => new Promise(r => setTimeout(r, ms));

            try {{
                const actionsBefore = document.querySelectorAll('message-actions').length;

                let interval = setInterval(() => {{
                    try {{
                        if (document.querySelectorAll('message-actions').length > actionsBefore) {{
                            const msgs = document.querySelectorAll('message-content');
                            const response = msgs[msgs.length - 1].innerText;

                            clearInterval(interval);
                            callback(response);
                        }}
                    }} catch (err) {{
                        clearInterval(interval);
                        callback("JS ERROR: " + err.message);
                    }}
                }}, 2000);

                async function run() {{
                    const input = document.querySelector('[data-placeholder="Ask Gemini"]');

                    if (!input) {{
                        callback("ERROR: Input not found");
                        return;
                    }}

                    input.focus();
                    document.execCommand('insertText', false, `{prompt}`);

                    await sleep(1000);

                    input.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter',
                        code: 'Enter',
                        bubbles: true
                    }}));
                }}

                run();

            }} catch (err) {{
                callback("JS FATAL ERROR: " + err.message);
            }}
        """)

        logging.info("Response received.")
        return result

    except Exception as e:
        logging.error(f"ask_gemini failed: {e}")
        return f"ERROR: {str(e)}"


# ---------------- MCP SERVER ----------------
async def mcp_server():
    global driver

    # Optional: Warm up the browser before entering the loop to prevent initial timeouts
    try:
        init_browser()
    except Exception as e:
        logging.error(f"Initial browser warm-up failed: {e}")

    try:
        while True:
            # Read from standard input
            line = await asyncio.to_thread(sys.stdin.readline)

            if not line:
                logging.info("STDIN closed. Exiting...")
                break

            try:
                req = json.loads(line)
                req_id = req.get("id")
                method = req.get("method")

                # Default response structure
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id
                }

                # 1. Handle Protocol Initialization
                if method == "initialize":
                    response["result"] = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "gemini-browser-bridge",
                            "version": "1.0.0"
                        }
                    }

                # 2. List available tools
                elif method == "tools/list":
                    response["result"] = {
                        "tools": [
                            {
                                "name": "ask_gemini",
                                "description": "Send a prompt to Gemini via the automated Edge browser",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string"}
                                    },
                                    "required": ["prompt"]
                                }
                            }
                        ]
                    }

                # 3. Execute tool calls
                elif method == "tools/call":
                    params = req.get("params", {})
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})

                    if tool_name == "ask_gemini":
                        prompt_text = arguments.get("prompt")
                        # Call your automation function
                        output = ask_gemini(prompt_text)

                        response["result"] = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(output)
                                }
                            ]
                        }
                    else:
                        response["error"] = {
                            "code": -32601,
                            "message": f"Tool not found: {tool_name}"
                        }

                # 4. Handle notifications (which have no ID)
                elif req_id is None:
                    continue

                    # 5. Unknown methods
                else:
                    response["error"] = {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }

                # Send the response back to the host
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            except json.JSONDecodeError:
                logging.error("Received invalid JSON")
            except Exception as e:
                logging.error(f"Error processing request: {e}")
                # Ensure we still send a valid JSON-RPC error if possible
                error_res = {
                    "jsonrpc": "2.0",
                    "id": req.get("id") if 'req' in locals() else None,
                    "error": {"code": -32603, "message": str(e)}
                }
                sys.stdout.write(json.dumps(error_res) + "\n")
                sys.stdout.flush()

    except Exception as e:
        logging.error(f"MCP server loop crashed: {e}")
    finally:
        logging.info("Shutting down MCP server...")
        if driver:
            try:
                driver.quit()
            except:
                pass

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    try:
        asyncio.run(mcp_server())
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(json.dumps({"error": str(e)}))
        sys.stdout.flush()
