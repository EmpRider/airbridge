# Testing the MCP Server

## Method 1: Direct stdin (Manual)

1. Run the server:
```bash
cd mcp-server
python playwright_mcp.py
```

2. In the same terminal, type this JSON and press Enter:
```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"test"}}}
```

## Method 2: Using test script (Easier)

1. Run the server:
```bash
cd mcp-server
python playwright_mcp.py
```

2. In another terminal, pipe the test request:
```bash
cd mcp-server
python test_request.py | python playwright_mcp.py
```

## Method 3: Echo command (Simplest)

Run everything in one command:
```bash
cd mcp-server
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"Hello"}}}' | python playwright_mcp.py
```

## Method 4: Using MCP Client (Production)

If you're using this with an MCP client (like Roo/Cline), configure it in your MCP settings:

```json
{
  "mcpServers": {
    "gemini-playwright": {
      "command": "python",
      "args": ["d:/web-chat/mcp-server/playwright_mcp.py"]
    }
  }
}
```

Then the client will handle sending requests automatically.

## Quick Test Commands

### Initialize
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python playwright_mcp.py
```

### List Tools
```bash
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python playwright_mcp.py
```

### Ask Gemini
```bash
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"What is the capital of France?"}}}' | python playwright_mcp.py
```

## Expected Output

You should see:
1. Browser window opens (if USE_HEADLESS=False)
2. Logs showing navigation and login prompt
3. JSON response with Gemini's answer

## Troubleshooting

### Browser doesn't appear
- Check `USE_HEADLESS` in config.py is `False`
- Check logs for "headless=False" confirmation

### Timeout errors
- Increase NAVIGATION_TIMEOUT in config.py
- Check internet connection
- Try different wait strategy

### No response
- Check if request JSON is valid
- Look at logs in ~/web-proxy/mcp_playwright.log
- Check error screenshots in ~/web-proxy/
