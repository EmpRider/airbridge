# Playwright MCP Server - Usage Guide

## Overview

This is a production-grade Playwright-based MCP (Model Context Protocol) server for Gemini browser automation with advanced anti-detection capabilities.

## Key Features

✅ **Playwright-based** - Modern, async browser automation
✅ **Stealth Mode** - playwright-stealth integration
✅ **New Headless Mode** - Chrome's undetectable headless engine
✅ **CDP-Level Masking** - Removes debugger traces
✅ **Telemetry Blocking** - Blocks analytics and tracking
✅ **Human-like Typing** - Variable speed with occasional typos
✅ **Hardware Fingerprint** - Realistic consumer device simulation
✅ **Persistent Sessions** - Login state preserved across requests
✅ **Long Response Support** - Handles responses up to 1 hour

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers

```bash
playwright install chrome
```

## Directory Structure

```
web-scraper/              # Original Selenium implementation (backup)
├── selenium_mcp.py       # Renamed from mcp.py
└── browser_state/

mcp-server/               # New Playwright implementation
├── playwright_mcp.py     # Main MCP server
├── config.py             # Configuration settings
├── stealth_utils.py      # Anti-detection utilities
└── browser_state/        # Persistent session storage
```

## Configuration

Edit [`mcp-server/config.py`](mcp-server/config.py) to customize:

```python
# Browser settings
USE_HEADLESS = True          # Use new headless mode
BROWSER_CHANNEL = "chrome"   # Browser to use

# Stealth features
BLOCK_TELEMETRY = True       # Block analytics
USE_HUMAN_TYPING = True      # Human-like typing
RANDOMIZE_HARDWARE = True    # Hardware fingerprint

# Timeouts
SCRIPT_TIMEOUT = 3600000     # 1 hour
PAGE_TIMEOUT = 3600000       # 1 hour
NAVIGATION_TIMEOUT = 60000   # 60 seconds
```

## Running the Server

### Standalone Mode

```bash
cd mcp-server
python playwright_mcp.py
```

### MCP Integration

Add to your MCP settings (e.g., `mcp_settings.json`):

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

## Usage

### Via MCP Tool

```python
# Call the ask_gemini tool
{
  "name": "ask_gemini",
  "arguments": {
    "prompt": "What is the capital of France?"
  }
}
```

### First Run

On first run, the browser will open and you'll need to:
1. Log in to your Google account
2. Navigate to Gemini
3. The session will be saved to `~/web-proxy/browser_state/state.json`
4. Subsequent runs will reuse this session

## Anti-Detection Features

### 1. Playwright-Stealth
Automatically patches common automation indicators.

### 2. CDP-Level Masking
Removes debugger traces that advanced detection systems look for:
- `window.chrome.runtime`
- `window.__playwright`
- `window.__pw_manual`
- Various webdriver properties

### 3. Telemetry Blocking
Blocks requests to:
- google-analytics.com
- googletagmanager.com
- doubleclick.net
- analytics.google.com

### 4. Human-like Typing
- Variable speed: 50-150ms per character
- 5% chance of typo + correction
- Random delays between actions

### 5. Hardware Fingerprint
- 8 CPU cores (realistic for consumer devices)
- 8GB RAM
- Consistent plugin list
- Realistic navigator properties

### 6. Consistent Headers
- User-Agent matches Chrome 120
- Sec-CH-UA headers aligned
- Realistic accept headers

## Comparison: Selenium vs Playwright

| Feature | Selenium | Playwright |
|---------|----------|------------|
| Detection Rate | High | Low |
| Headless Mode | Old (detectable) | New (undetectable) |
| API Style | Sync | Async |
| Speed | Slower | Faster |
| Stealth Library | ❌ | ✅ |
| CDP Control | ❌ | ✅ |
| Telemetry Blocking | Manual | Built-in |
| Session Persistence | Complex | Simple |

## Troubleshooting

### Browser Not Found

```bash
playwright install chrome
```

### Import Errors

```bash
pip install playwright playwright-stealth
```

### Session Not Persisting

Check that `~/web-proxy/browser_state/` directory exists and is writable.

### Detection Issues

1. Ensure `USE_HEADLESS = True` (new headless mode)
2. Verify `BLOCK_TELEMETRY = True`
3. Enable `USE_HUMAN_TYPING = True`
4. Check logs in `~/web-proxy/mcp_playwright.log`

### Timeout Errors

For very long responses, timeouts are set to 1 hour. If needed, adjust in [`config.py`](mcp-server/config.py):

```python
SCRIPT_TIMEOUT = 7200000  # 2 hours
PAGE_TIMEOUT = 7200000    # 2 hours
```

## Logs

Logs are written to:
- **Console**: stderr (MCP-safe)
- **File**: `~/web-proxy/mcp_playwright.log`

Log levels:
- DEBUG: Detailed execution info
- INFO: Key events
- ERROR: Failures and exceptions

## Error Screenshots

On errors, screenshots are automatically saved to:
```
~/web-proxy/error_YYYYMMDD_HHMMSS.png
```

## Expert Recommendations Implemented

Based on Gemini expert review ([`plans/gemini-expert-review.md`](../plans/gemini-expert-review.md)):

✅ CDP-level property masking
✅ Request interception for telemetry
✅ Human-like typing cadence
✅ Hardware concurrency & memory randomization
✅ Consistent User-Agent and Sec-CH-UA headers
✅ New headless mode
✅ Playwright-stealth integration

## Performance

- **Startup**: ~2-3 seconds
- **Navigation**: ~3-5 seconds
- **Typing**: Variable (human-like)
- **Response**: Depends on Gemini (up to 1 hour supported)

## Security Notes

- Session tokens are stored in `~/web-proxy/browser_state/state.json`
- Protect this file as it contains authentication data
- Logs may contain sensitive information
- Use appropriate file permissions

## Migration from Selenium

The original Selenium implementation is preserved in [`web-scraper/selenium_mcp.py`](../web-scraper/selenium_mcp.py) for reference and backup.

To switch back to Selenium (not recommended):
```bash
cd web-scraper
python selenium_mcp.py
```

## Support

For issues or questions:
1. Check logs in `~/web-proxy/mcp_playwright.log`
2. Review error screenshots
3. Verify configuration in [`config.py`](mcp-server/config.py)
4. Consult [`plans/selenium-to-playwright-conversion.md`](../plans/selenium-to-playwright-conversion.md)

## Version

**Current Version**: 6.0.0 (Playwright with Expert Enhancements)
**Previous Version**: 5.1.0 (Selenium)

## License

Same as parent project.
