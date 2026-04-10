# Gemini MCP Server (Undetected-ChromeDriver)

Clean, simple MCP server for Gemini automation using undetected-chromedriver to bypass bot detection.

## Features

✅ **No Bot Detection** - Uses undetected-chromedriver (proven with Google services)
✅ **Auto-Patching** - Automatically patches ChromeDriver binary
✅ **Session Persistence** - Chrome profile maintains login across requests
✅ **Human-like Typing** - Variable speed with occasional typos
✅ **Simple Code** - ~250 lines vs 500+ with Playwright
✅ **MCP Compatible** - Full Model Context Protocol support

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs `undetected-chromedriver` which will auto-download ChromeDriver on first run.

### 2. First Run (Manual Login)

```bash
cd gemini-mcp
python undetected_mcp.py
```

Send a test request:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"test"}}}' | python undetected_mcp.py
```

**Browser will open** - Log in to your Google account manually. The session will be saved to `~/web-proxy/chrome-profile/`.

### 3. Enable Headless Mode

After successful login, edit [`config.py`](config.py):
```python
USE_HEADLESS = True  # Change to True
```

### 4. Use the Server

Now it runs in background with your saved session:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"What is 2+2?"}}}' | python undetected_mcp.py
```

## Configuration

Edit [`config.py`](config.py) to customize:

```python
# Browser
USE_HEADLESS = False  # False for first login, True for production
WINDOW_SIZE = (1920, 1080)

# Typing behavior
USE_HUMAN_TYPING = True  # Human-like typing with delays
TYPING_DELAY_MIN = 0.05  # Min delay between keys
TYPING_DELAY_MAX = 0.15  # Max delay between keys
TYPO_PROBABILITY = 0.05  # 5% chance of typo

# Timeouts
SCRIPT_TIMEOUT = 3600  # 1 hour for long responses
PAGE_LOAD_TIMEOUT = 60  # 60 seconds
```

## MCP Integration

Add to your MCP settings (e.g., `mcp_settings.json`):

```json
{
  "mcpServers": {
    "gemini": {
      "command": "python",
      "args": ["d:/web-chat/gemini-mcp/undetected_mcp.py"],
      "env": {}
    }
  }
}
```

## File Structure

```
gemini-mcp/
├── undetected_mcp.py    # Main MCP server (~250 lines)
├── config.py            # Configuration settings
├── utils.py             # Helper functions
├── README.md            # This file
└── chrome-profile/      # Chrome user data (auto-created)
```

## How It Works

### 1. Undetected-ChromeDriver
- Automatically patches ChromeDriver binary
- Removes all automation indicators
- Bypasses Google's bot detection
- Works with Google services (Gmail, Gemini, etc.)

### 2. Session Persistence
- Uses Chrome's native profile system
- Login saved to `chrome-profile/Default/`
- No manual session management needed
- Works across restarts

### 3. Human-like Behavior
- Variable typing speed (50-150ms per character)
- Occasional typos with corrections (5% chance)
- Random delays between actions
- Natural interaction patterns

## Troubleshooting

### ChromeDriver Not Found
Undetected-chromedriver will auto-download on first run. If issues persist:
```bash
pip install --upgrade undetected-chromedriver
```

### Login Not Persisting
Check that `~/web-proxy/chrome-profile/` exists and is writable:
```bash
# Windows
dir %USERPROFILE%\web-proxy\chrome-profile

# Linux/Mac
ls -la ~/web-proxy/chrome-profile
```

### Still Detected
1. Make sure you're using the latest version:
   ```bash
   pip install --upgrade undetected-chromedriver
   ```

2. Try non-headless mode first:
   ```python
   USE_HEADLESS = False
   ```

3. Check logs:
   ```bash
   tail -f ~/web-proxy/gemini_mcp.log
   ```

## Logs

Logs are written to:
- **Console**: stderr (MCP-safe)
- **File**: `~/web-proxy/gemini_mcp.log`

## Comparison with Playwright

| Feature | Playwright | Undetected-ChromeDriver |
|---------|-----------|------------------------|
| Detection | High | Very Low ✅ |
| Code Complexity | 500+ lines | 250 lines ✅ |
| Setup | Complex | Simple ✅ |
| Session Management | Manual JSON | Native Chrome ✅ |
| Maintenance | Manual updates | Auto-updates ✅ |
| Google Services | Blocked | Works ✅ |

## Why This Works

Undetected-chromedriver:
1. **Patches ChromeDriver binary** - Removes automation signatures at the binary level
2. **Proven track record** - Used by 10,000+ developers for Google services
3. **Active development** - Constantly updated for new detection methods
4. **Native Chrome profile** - Uses Chrome's built-in session management

## Version

**Version**: 1.0.0
**Status**: Production Ready
**Detection Rate**: Very Low

## Support

For issues:
1. Check logs in `~/web-proxy/gemini_mcp.log`
2. Verify Chrome profile exists
3. Try non-headless mode first
4. Update undetected-chromedriver

## License

Same as parent project.
