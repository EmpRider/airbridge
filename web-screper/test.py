import subprocess
import json
import time
import sys

# --- CONFIGURATION ---
# Replace this with the actual name of your server file
SERVER_SCRIPT_NAME = "mcp.py"


def send_request(process, request_payload):
    """Sends a JSON-RPC request to the MCP server and reads the response."""
    # 1. Convert dictionary to JSON string and add a newline
    req_str = json.dumps(request_payload) + "\n"

    print(f"[\033[94mSENDING\033[0m]  {req_str.strip()}")

    # 2. Write to the server's stdin and flush the buffer
    process.stdin.write(req_str)
    process.stdin.flush()

    # 3. Read the response from the server's stdout
    response_str = process.stdout.readline()

    if response_str:
        print(f"[\033[92mRECEIVED\033[0m] {response_str.strip()}\n")
        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            print("[\033[91mERROR\033[0m] Failed to parse JSON response.")
            return None
    else:
        print("[\033[91mERROR\033[0m] No response received. Server might have crashed.")
        return None


def main():
    print("Starting MCP Server Test Client...\n")
    print("-" * 50)

    # Launch the server as a subprocess
    try:
        process = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT_NAME],  # Uses the current python interpreter
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr separately so logging doesn't break JSON parsing
            text=True  # Handles string decoding automatically
        )
    except FileNotFoundError:
        print(f"Error: Could not find the server script '{SERVER_SCRIPT_NAME}'.")
        return

    try:
        # --- TEST 1: Initialization ---
        # The host always sends this first to negotiate capabilities
        req_init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize"
        }
        send_request(process, req_init)
        time.sleep(1)  # Slight pause to simulate real-world pacing

        # --- TEST 2: List Tools ---
        # The host asks the server what tools are available
        req_tools = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        send_request(process, req_tools)
        time.sleep(1)

        # --- TEST 3: Call a Tool ---
        # The host attempts to execute the 'ask_gemini' tool
        req_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ask_gemini",
                "arguments": {
                    "prompt": "Hello Gemini, what is the capital of France?"
                }
            }
        }
        send_request(process, req_call)
        time.sleep(2)  # Give the automation script time to run

        # --- TEST 4: Error Handling (Optional) ---
        # Testing an unknown method to ensure the server doesn't crash
        req_error = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "unknown/method"
        }
        send_request(process, req_error)

    finally:
        # Cleanup: terminate the server process when done
        print("-" * 50)
        print("Tests complete. Shutting down server process...")
        process.terminate()

        # Print any logs that were sent to stderr by the server
        stderr_output = process.stderr.read()
        if stderr_output:
            print("\n--- Server Error/Log Output ---")
            print(stderr_output)


if __name__ == "__main__":
    main()