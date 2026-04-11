# MCP Server Hang Issue - Fix Summary

## Problem Description
The MCP server would hang when the LLM agent called `query_premium_model` with correct parameters. The browser window would not open even with `--no-headless` flag, and the agent would wait indefinitely for a response.

## Updates (2026-04-11)

### New Feature: Temporary Chat Control
Added `--use-temp-chat` and `--no-temp-chat` CLI arguments to control whether to use Gemini's temporary chat mode.

**Default behavior:** Temporary chat is ENABLED by default (more private, no history saved)

**Usage:**
```bash
# Use temporary chat (default)
python main.py --use-temp-chat

# Use normal chat with history
python main.py --no-temp-chat
```

**MCP Configuration:**
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

**Note:** The temp chat setting is configured via CLI arguments only, not as an MCP tool parameter. This ensures consistent behavior across all requests in a session.

## Root Causes Identified

### 1. **Singleton Configuration Not Updating**
**Location:** `mcp_manager/browser.py:156-161`

The `get_browser_config()` function used a singleton pattern that ignored parameter updates after initial creation:

```python
# OLD CODE - BROKEN
def get_browser_config(chrome_path=None, headless=None, profile_dir=None):
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    return _browser_config  # Ignores new parameters!
```

**Issue:** When CLI args set `--no-headless`, the config was created with `headless=False`. But when the adapter later called `get_browser_config(chrome_path, headless)` with `headless=None`, the singleton would return the existing config without updating, potentially using stale settings.

**Fix:** Modified the singleton to update non-None parameters:

```python
# NEW CODE - FIXED
def get_browser_config(chrome_path=None, headless=None, profile_dir=None):
    global _browser_config
    if _browser_config is None:
        _browser_config = BrowserConfig(chrome_path, headless, profile_dir)
    else:
        # Update existing config with non-None parameters
        if chrome_path is not None:
            _browser_config.chrome_path = chrome_path
            _browser_config.chrome_executable = validate_chrome(chrome_path)
        if headless is not None:
            _browser_config.headless = headless
        if profile_dir is not None:
            _browser_config.profile_dir = profile_dir
            _browser_config.profile_dir.mkdir(parents=True, exist_ok=True)
    return _browser_config
```

### 2. **Method Signature Mismatch**
**Location:** `mcp_manager/adapters/base_adapter.py:24`

The abstract base class `BaseAdapter.process()` was missing the `model` parameter:

```python
# OLD CODE - BROKEN
@abstractmethod
def process(self, prompt, chrome_path=None, headless=None):
```

But the implementation in `GeminiAdapter` and the call in `server.py` both used:

```python
def process(self, prompt, model, chrome_path=None, headless=None):
```

**Fix:** Updated the base class signature to include `model`:

```python
# NEW CODE - FIXED
@abstractmethod
def process(self, prompt, model, chrome_path=None, headless=None):
```

### 3. **Insufficient Logging**
**Location:** `mcp_manager/server.py:154-180`

The server had minimal logging, making it hard to diagnose where the hang occurred.

**Fix:** Added detailed logging:
- Log tool call parameters
- Log adapter creation
- Log when background thread starts
- Log when adapter completes
- Better error handling with specific error messages

### 4. **Missing Profile Directory Parameter**
**Location:** `mcp_manager/adapters/gemini/gemini_adapter.py:43`

The adapter was calling `get_browser_config(chrome_path, headless)` without the profile_dir parameter, which could cause issues.

**Fix:** Updated to pass all three parameters:

```python
config = get_browser_config(chrome_path, headless, None)
logger.info(f"Browser config: headless={config.headless}, chrome={config.chrome_executable}")
```

## Files Modified

1. **mcp_manager/browser.py**
   - Updated `get_browser_config()` to support parameter updates on existing singleton

2. **mcp_manager/adapters/base_adapter.py**
   - Added `model` parameter to abstract `process()` method signature

3. **mcp_manager/adapters/gemini/gemini_adapter.py**
   - Updated `get_browser_config()` call to pass profile_dir parameter
   - Added logging for browser config settings

4. **mcp_manager/server.py**
   - Added comprehensive logging for tool calls
   - Added better error handling and exception logging

## Testing

Created `test_mcp_fix.py` to verify:
1. Browser config singleton updates correctly when parameters change
2. Adapter has correct method signature with all required parameters

Both tests pass successfully.

## How to Use

Your MCP configuration should now work correctly:

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

The browser will now properly open in windowed mode when `--no-headless` is specified, and the MCP server will respond correctly to tool calls.

## Debugging

If issues persist, check the log file at:
- Windows: `C:\Users\<username>\web-proxy\gemini_mcp.log`

The enhanced logging will show:
- Tool call parameters received
- Browser config settings (headless mode, chrome path)
- Adapter creation and execution progress
- Detailed error messages if failures occur
