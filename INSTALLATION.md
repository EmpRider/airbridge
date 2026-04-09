# Installation and Testing Guide

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `playwright>=1.40.0` - Modern browser automation
- `playwright-stealth>=1.0.0` - Anti-detection patches

### 2. Install Playwright Browsers

```bash
playwright install chrome
```

This downloads the Chrome browser for Playwright to use.

### 3. Verify Installation

```bash
cd mcp-server
python -c "import playwright; from playwright_stealth import stealth_async; print('✅ All dependencies installed')"
```

## Testing the Implementation

### Test 1: Syntax Check

```bash
cd mcp-server
python -m py_compile playwright_mcp.py config.py stealth_utils.py
```

Expected: No output (success)

### Test 2: Import Check

```bash
cd mcp-server
python -c "from playwright_mcp import mcp_server; print('✅ Imports successful')"
```

### Test 3: Configuration Check

```bash
cd mcp-server
python -c "from config import *; print(f'✅ Config loaded: {GEMINI_URL}')"
```

### Test 4: Stealth Utils Check

```bash
cd mcp-server
python -c "from stealth_utils import *; print('✅ Stealth utils loaded')"
```

### Test 5: Run MCP Server (Manual Test)

```bash
cd mcp-server
python playwright_mcp.py
```

Then send a test MCP request via stdin:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
```

Expected response:
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{},"resources":{},"prompts":{}},"serverInfo":{"name":"gemini-playwright-bridge","version":"6.0.0"}}}
```

Press Ctrl+C to stop.

### Test 6: Full Integration Test

Create a test script [`test_gemini.py`](test_gemini.py):

```python
import asyncio
import sys
sys.path.insert(0, 'mcp-server')

from playwright_mcp import ask_gemini_playwright

async def test():
    print("Testing Gemini automation...")
    response = await ask_gemini_playwright("What is 2+2?")
    print(f"Response: {response}")
    
    if "4" in response or "four" in response.lower():
        print("✅ Test passed!")
    else:
        print("⚠️ Unexpected response")

if __name__ == "__main__":
    asyncio.run(test())
```

Run:
```bash
python test_gemini.py
```

**Note**: On first run, you'll need to log in to Google/Gemini manually.

## Comparison Test: Selenium vs Playwright

### Run Selenium Version (Old)

```bash
cd web-scraper
python selenium_mcp.py
```

### Run Playwright Version (New)

```bash
cd mcp-server
python playwright_mcp.py
```

### Compare Detection Rates

Monitor for:
- ❌ CAPTCHA challenges
- ❌ "Unusual traffic" warnings
- ❌ Login blocks
- ✅ Smooth operation

## Troubleshooting

### Error: "playwright not found"

```bash
pip install playwright
playwright install chrome
```

### Error: "playwright_stealth not found"

```bash
pip install playwright-stealth
```

### Error: "Chrome not found"

```bash
playwright install chrome
```

### Error: "Permission denied" on state file

```bash
# Windows
mkdir %USERPROFILE%\web-proxy\browser_state

# Linux/Mac
mkdir -p ~/web-proxy/browser_state
chmod 755 ~/web-proxy/browser_state
```

### Browser Opens But Doesn't Navigate

Check logs:
```bash
tail -f ~/web-proxy/mcp_playwright.log
```

Look for navigation errors or timeout issues.

### Detection Issues

1. Verify headless mode is enabled:
   ```python
   # In config.py
   USE_HEADLESS = True
   ```

2. Check telemetry blocking:
   ```python
   # In config.py
   BLOCK_TELEMETRY = True
   ```

3. Enable human typing:
   ```python
   # In config.py
   USE_HUMAN_TYPING = True
   ```

## Performance Benchmarks

Expected performance:

| Operation | Time |
|-----------|------|
| Browser Launch | 2-3s |
| Navigation | 3-5s |
| Typing (100 chars) | 5-15s (human-like) |
| Response Wait | Variable (up to 1 hour) |
| Total (short prompt) | 10-25s |

## Next Steps

After successful testing:

1. ✅ Verify all tests pass
2. ✅ Confirm no detection issues
3. ✅ Update MCP settings to use new server
4. ✅ Monitor logs for any issues
5. ✅ Keep Selenium version as backup

## MCP Integration

Update your MCP settings file:

```json
{
  "mcpServers": {
    "gemini-playwright": {
      "command": "python",
      "args": ["d:/web-chat/mcp-server/playwright_mcp.py"],
      "env": {}
    }
  }
}
```

Restart your MCP client to load the new server.

## Success Criteria

✅ All imports successful
✅ Browser launches without errors
✅ Navigation to Gemini works
✅ Login session persists
✅ Prompts are submitted successfully
✅ Responses are received
✅ No CAPTCHA or detection warnings
✅ Logs show no errors

## Support

If issues persist:
1. Check [`mcp-server/README.md`](mcp-server/README.md)
2. Review [`plans/selenium-to-playwright-conversion.md`](plans/selenium-to-playwright-conversion.md)
3. Consult [`plans/gemini-expert-review.md`](plans/gemini-expert-review.md)
4. Check logs in `~/web-proxy/mcp_playwright.log`
