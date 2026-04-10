# MCP Server Restart Instructions

## Problem
The ask-gemini MCP server was experiencing a "Binary Location Must be a String" error because the Chrome binary path wasn't being set correctly.

## Solution Applied
We've fixed the issue by:

1. **Updated [`config.py`](config.py)**
   - Added `get_chrome_path()` function to auto-detect Chrome installation
   - Added `CHROME_BINARY_PATH` configuration variable
   - Supports Windows, macOS, and Linux
   - Allows override via `CHROME_PATH` environment variable

2. **Updated [`undetected_mcp.py`](undetected_mcp.py)**
   - Added validation to ensure Chrome is found before launching
   - Set `options.binary_location = CHROME_BINARY_PATH`
   - Pass `browser_executable_path=CHROME_BINARY_PATH` to `uc.Chrome()`
   - Added helpful error messages if Chrome is not found

## Verification
The test script [`test_chrome_path.py`](test_chrome_path.py) confirms:
- ✓ Chrome path detected: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- ✓ Configuration loads correctly
- ✓ `binary_location` is set as a string
- ✓ All configuration tests pass

## How to Restart the MCP Server

The MCP server is managed by your IDE (Roo/VSCode). To apply the changes:

### Option 1: Restart IDE (Recommended)
1. Close VSCode/Roo completely
2. Reopen VSCode/Roo
3. The MCP server will automatically restart with the new code

### Option 2: Reload Window (Faster)
1. In VSCode, press `Ctrl+Shift+P` (Windows) or `Cmd+Shift+P` (Mac)
2. Type "Reload Window" and select it
3. The MCP server will restart

### Option 3: Disable/Enable MCP Server
1. Open MCP settings: `c:\Users\Empire Rider\AppData\Roaming\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json`
2. Set `"disabled": true` for ask-gemini
3. Save the file
4. Set `"disabled": false`
5. Save again

## Testing After Restart

Once the MCP server is restarted, test it with:

```
Ask Roo to call: mcp--ask-gemini--ask_gemini("What is 2+2?")
```

Expected result: Gemini should respond with the answer.

## Current MCP Configuration

Location: `c:\Users\Empire Rider\AppData\Roaming\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json`

```json
{
  "mcpServers": {
    "ask-gemini": {
      "command": "python",
      "args": [
        "D:\\web-chat\\gemini-mcp\\undetected_mcp.py"
      ],
      "disabled": false,
      "alwaysAllow": [
        "ask_gemini"
      ],
      "timeout": 3600
    }
  }
}
```

## Troubleshooting

### If the error persists after restart:

1. **Check Chrome installation**
   ```bash
   cd gemini-mcp
   python -c "from config import CHROME_BINARY_PATH; print(CHROME_BINARY_PATH)"
   ```
   Should output: `C:\Program Files\Google\Chrome\Application\chrome.exe`

2. **Run the test script**
   ```bash
   cd gemini-mcp
   python test_chrome_path.py
   ```
   All tests should pass.

3. **Check MCP server logs**
   ```bash
   type "%USERPROFILE%\web-proxy\gemini_mcp.log"
   ```
   Look for recent entries showing the Chrome path being used.

4. **Manual Chrome path override**
   If auto-detection fails, set environment variable:
   ```bash
   set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
   ```
   Then restart the MCP server.

## Next Steps

After restarting:
1. Test the MCP server with a simple prompt
2. If successful, you can enable headless mode by setting `USE_HEADLESS = True` in [`config.py`](config.py)
3. The first run will require manual login to Gemini (browser will open)
4. After login, the session will be saved and subsequent runs will be automatic

## Files Modified

- [`gemini-mcp/config.py`](config.py) - Added Chrome path detection
- [`gemini-mcp/undetected_mcp.py`](undetected_mcp.py) - Added Chrome binary configuration
- [`gemini-mcp/test_chrome_path.py`](test_chrome_path.py) - New test script
- [`docs/plans/ask-gemini-mcp-fix.md`](../docs/plans/ask-gemini-mcp-fix.md) - Detailed fix plan
