# MCP Server Troubleshooting Guide

## Quick Diagnostics

### 1. Check Log File
The MCP server logs everything to:
```
C:\Users\<YourUsername>\web-proxy\gemini_mcp.log
```

Look for these key log entries:
- `Tool call parameters:` - Shows what parameters the MCP received
- `Browser config:` - Shows the actual headless setting being used
- `Chrome launched successfully` - Confirms browser started
- `Adapter.process() completed` - Confirms the request finished

### 2. Test the MCP Server Manually

Run the test script:
```bash
python test_mcp_fix.py
```

This verifies:
- Browser config singleton updates correctly
- Adapter has correct method signature

### 3. Test Browser Launch

Test if Chrome launches correctly:
```bash
python main.py --no-headless
```

Then send a test JSON-RPC request via stdin (or use your MCP client).

## Common Issues

### Issue: Browser doesn't open in windowed mode

**Symptoms:**
- You set `--no-headless` but browser stays hidden
- MCP hangs waiting for response

**Solution:**
The fixes applied should resolve this. The singleton now properly updates the headless setting.

**Verify:**
Check the log file for:
```
Browser config: headless=False, chrome=...
```

### Issue: MCP server hangs indefinitely

**Symptoms:**
- Agent calls `query_premium_model` with correct params
- No response for 6-10 minutes
- No browser window appears

**Possible Causes:**
1. Chrome not found - Check log for "Chrome not found" error
2. Chrome profile locked - Close other Chrome instances
3. Network timeout - Check internet connection
4. Login required - Browser needs manual Google login

**Solution:**
1. Check log file for specific error
2. Ensure Chrome is installed and accessible
3. Try running with `--no-headless` first to see what's happening
4. If login required, the browser will automatically switch to windowed mode

### Issue: "Chrome not found" error

**Solution:**
Set Chrome path explicitly:
```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--chrome-path", "C:/Program Files/Google/Chrome/Application/chrome.exe",
      "--no-headless"
    ]
  }
}
```

Or set environment variable:
```bash
set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

### Issue: Login timeout

**Symptoms:**
- Browser opens to Google login page
- After 5 minutes: "ERROR: Login timed out"

**Solution:**
1. Log in within 5 minutes when browser opens
2. The session will be saved in the Chrome profile
3. Future requests won't require login

## Configuration Examples

### Minimal (auto-detect Chrome, headless mode, temp chat enabled)
```json
{
  "query_premium_model": {
    "command": "python",
    "args": ["D:\\web-chat\\main.py"]
  }
}
```

### Windowed mode (for debugging)
```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--no-headless"
    ]
  }
}
```

### Disable temporary chat (use normal chat with history)
```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--no-temp-chat"
    ]
  }
}
```

### Custom Chrome path
```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--chrome-path", "C:/Program Files/Google/Chrome/Application/chrome.exe",
      "--no-headless"
    ]
  }
}
```

### Full configuration example
```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--chrome-path", "C:/Program Files/Google/Chrome/Application/chrome.exe",
      "--profile-dir", "D:/my-chrome-profile",
      "--no-headless",
      "--no-temp-chat"
    ]
  }
}
```

## Temporary Chat Mode

**What is temporary chat?**
- Temporary chat mode in Gemini doesn't save conversation history
- More private - conversations are not stored in your Google account
- Enabled by default for privacy

**When to disable temporary chat:**
- You want to review conversation history later
- You're building a persistent chat session
- You need to access the conversation from Gemini's web interface

**How to control:**

CLI:
```bash
# Enable temp chat (default)
python main.py --use-temp-chat

# Disable temp chat
python main.py --no-temp-chat
```

MCP tool parameter:
```json
{
  "prompt": "Your question",
  "task": "thinking",
  "model": "Fast",
  "use_temp_chat": false
}
```

## Testing the Fix

### Test 1: Verify fixes applied
```bash
python test_mcp_fix.py
```

Expected output:
```
Testing browser config singleton updates...
Initial config: headless=True
Updated config: headless=False
[PASS] Browser config singleton updates correctly

Testing adapter signature...
Created adapter: <GeminiAdapter task='thinking' adapter='gemini'>
Process method parameters: ['prompt', 'model', 'chrome_path', 'headless']
[PASS] Adapter signature is correct

==================================================
All tests passed!
==================================================
```

### Test 2: Manual MCP call

1. Start the server:
```bash
python main.py --no-headless
```

2. Send a test request (via your MCP client or manually):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "query_premium_model",
    "arguments": {
      "prompt": "What is 2+2?",
      "task": "thinking",
      "model": "Fast"
    }
  }
}
```

3. Check the log file for progress

## Getting Help

If issues persist after applying these fixes:

1. **Collect logs:**
   - Copy the full log file: `C:\Users\<YourUsername>\web-proxy\gemini_mcp.log`
   - Note the exact error message
   - Note when the hang occurs (before/after browser launch)

2. **Provide details:**
   - Your MCP configuration JSON
   - Chrome version: `chrome --version`
   - Python version: `python --version`
   - Operating system version

3. **Try debug mode:**
   Run with `--no-headless` to see what the browser is doing

## Changes Made (2026-04-11)

Fixed the MCP server hang issue by:

1. **Updated browser config singleton** to accept parameter updates after initialization
2. **Fixed method signature mismatch** - added `model` parameter to base adapter
3. **Enhanced logging** throughout the request lifecycle
4. **Improved error handling** with specific error messages

See [MCP_FIX_SUMMARY.md](MCP_FIX_SUMMARY.md) for technical details.
