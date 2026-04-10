"""
Simple test script to send requests to the MCP server
Run this in a separate terminal while the MCP server is running
"""
import json
import sys

def send_mcp_request(method, params=None):
    """Send an MCP request to stdin"""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {}
    }
    print(json.dumps(request))
    sys.stdout.flush()

if __name__ == "__main__":
    # Test: Ask Gemini a simple question
    send_mcp_request("tools/call", {
        "name": "ask_gemini",
        "arguments": {
            "prompt": "What is 2+2?"
        }
    })
