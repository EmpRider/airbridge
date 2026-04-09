# Selenium to Playwright Conversion Plan

## Overview
Convert the existing Selenium-based Gemini browser automation ([`web-screper/mcp.py`](../web-screper/mcp.py)) to use Playwright instead, with enhanced anti-detection capabilities to avoid bot detection.

## Problem Statement
The current Selenium implementation is being detected as automation by Gemini, which can lead to:
- Blocked requests
- CAPTCHA challenges
- Session termination
- Degraded functionality

## Why Playwright?
Playwright offers several advantages over Selenium for avoiding detection:

1. **Better Stealth by Default**: Playwright has fewer automation fingerprints
2. **Native Async Support**: Better performance and resource management
3. **Built-in Context Isolation**: Cleaner session management
4. **Modern Browser APIs**: More reliable element interaction
5. **Better Network Control**: Can intercept and modify requests
6. **Persistent Contexts**: Easier login session management

## Key Functionality to Preserve

### Core Features
- MCP (Model Context Protocol) server implementation
- Async JSON-RPC communication via stdin/stdout
- Gemini web interface automation
- Persistent login session across requests
- Long timeout support (1 hour for responses)
- Comprehensive logging to file and stderr

### MCP Protocol Methods
- `initialize` - Server initialization
- `tools/list` - List available tools
- `tools/call` - Execute ask_gemini tool
- `resources/list` - Empty resources list
- `resources/templates/list` - Empty templates list
- `prompts/list` - Empty prompts list

### Browser Automation Flow
1. Launch browser with persistent profile
2. Navigate to Gemini URL
3. Wait for page load
4. Inject JavaScript to interact with Gemini UI
5. Submit prompt via simulated user input
6. Poll for response completion
7. Extract and return response text
8. Close browser

## Playwright Anti-Detection Strategy

### 1. Stealth Configuration
```python
# Use persistent context with real user profile
context = await browser.new_context(
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    viewport={'width': 1920, 'height': 1080},
    locale='en-US',
    timezone_id='America/New_York',
    permissions=['geolocation', 'notifications'],
    color_scheme='light',
    storage_state=storage_state_path  # Persist login
)
```

### 2. Browser Fingerprint Masking
- Remove `navigator.webdriver` flag
- Mask automation indicators
- Use real Chrome/Edge user agent
- Enable JavaScript and cookies
- Set realistic viewport sizes

### 3. Human-like Behavior
- Random delays between actions
- Gradual typing instead of instant text insertion
- Mouse movement simulation (optional)
- Realistic timing for interactions

### 4. Persistent Browser Context
- Store authentication state to disk
- Reuse browser profile across sessions
- Maintain cookies and local storage
- Avoid repeated logins

## Architecture Changes

### File Structure
```
web-screper/
├── mcp.py                    # Original Selenium version (keep for reference)
├── mcp_playwright.py         # New Playwright implementation
└── browser_state/            # Persistent browser context storage
    └── state.json            # Authentication state
```

### Dependencies Update
```txt
# requirements.txt
playwright>=1.40.0
playwright-stealth>=1.0.0  # Optional: additional stealth patches
```

### Configuration Changes
```python
# New constants
BASE_DIR = Path.home() / "web-proxy"
BROWSER_STATE_DIR = BASE_DIR / "browser_state"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
LOG_FILE = BASE_DIR / "mcp_playwright.log"

# Timeout configuration (unchanged)
SCRIPT_TIMEOUT = 3600  # 1 hour
PAGE_TIMEOUT = 3600    # 1 hour
```

## Implementation Details

### 1. Browser Launch
```python
async def get_browser():
    """Launch Playwright browser with anti-detection settings"""
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=False,  # Headless mode is more detectable
        channel="msedge",  # Use Edge like original
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process'
        ]
    )
    
    return playwright, browser
```

### 2. Context Management
```python
async def get_context(browser):
    """Create or load persistent browser context"""
    if STATE_FILE.exists():
        # Load existing session
        context = await browser.new_context(
            storage_state=str(STATE_FILE)
        )
    else:
        # Create new session
        context = await browser.new_context()
    
    # Apply anti-detection patches
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    return context
```

### 3. Gemini Interaction
```python
async def ask_gemini_playwright(prompt: str) -> str:
    """Send prompt to Gemini using Playwright"""
    playwright, browser = await get_browser()
    context = await get_context(browser)
    page = await context.new_page()
    
    try:
        # Navigate to Gemini
        await page.goto(GEMINI_URL, wait_until='networkidle', timeout=60000)
        
        # Wait for input field
        input_selector = '[data-placeholder="Ask Gemini"]'
        await page.wait_for_selector(input_selector, timeout=30000)
        
        # Type prompt with human-like delays
        await page.type(input_selector, prompt, delay=50)
        
        # Press Enter
        await page.keyboard.press('Enter')
        
        # Wait for response with polling
        response = await page.evaluate("""
            async () => {
                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                let lastLength = 0;
                let stableCount = 0;
                
                while (true) {
                    const msgs = document.querySelectorAll('message-content');
                    if (msgs.length > 0) {
                        const last = msgs[msgs.length - 1].innerText;
                        const currentLength = last ? last.length : 0;
                        
                        if (currentLength > 20) {
                            if (currentLength === lastLength) {
                                stableCount++;
                                if (stableCount >= 3) {
                                    return last;
                                }
                            } else {
                                stableCount = 0;
                                lastLength = currentLength;
                            }
                        }
                    }
                    await sleep(1000);
                }
            }
        """)
        
        # Save session state
        await context.storage_state(path=str(STATE_FILE))
        
        return response
        
    finally:
        await page.close()
        await context.close()
        await browser.close()
        await playwright.stop()
```

### 4. MCP Server Integration
The MCP server structure remains identical, only the `ask_gemini()` function is replaced with the async Playwright version. The async nature requires updating the tool call handler:

```python
elif method == "tools/call":
    params = req.get("params", {})
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if tool_name == "ask_gemini":
        prompt = arguments.get("prompt", "")
        # Run async function in sync context
        output = await ask_gemini_playwright(prompt)
        
        response["result"] = {
            "content": [{"type": "text", "text": output}]
        }
```

## Migration Steps

### Phase 1: Setup
1. Install Playwright: `pip install playwright`
2. Install browsers: `playwright install chromium msedge`
3. Create browser state directory structure
4. Update requirements.txt

### Phase 2: Implementation
1. Create [`mcp_playwright.py`](../web-screper/mcp_playwright.py) with new implementation
2. Copy MCP server boilerplate from original
3. Implement Playwright browser launch with anti-detection
4. Implement persistent context management
5. Port Gemini interaction logic to Playwright
6. Add comprehensive error handling

### Phase 3: Testing
1. Test browser launch and context creation
2. Test Gemini navigation and login persistence
3. Test prompt submission and response extraction
4. Test MCP protocol communication
5. Test long-running responses (timeout handling)
6. Compare detection rates with Selenium version

### Phase 4: Optimization
1. Fine-tune anti-detection parameters
2. Optimize timeout configurations
3. Add retry logic for transient failures
4. Improve logging and debugging output

## Key Differences from Selenium

| Aspect | Selenium | Playwright |
|--------|----------|------------|
| API Style | Synchronous | Async/await |
| Browser Control | WebDriver protocol | CDP (Chrome DevTools Protocol) |
| Element Interaction | `find_element()` | `page.locator()` |
| JavaScript Execution | `execute_script()` | `page.evaluate()` |
| Waiting | Implicit/explicit waits | Auto-waiting built-in |
| Context Isolation | Limited | Native support |
| Network Interception | Complex | Built-in |
| Detection Fingerprint | Higher | Lower |

## Anti-Detection Checklist

- [ ] Remove `navigator.webdriver` flag
- [ ] Use real user agent strings
- [ ] Set realistic viewport dimensions
- [ ] Enable JavaScript and cookies
- [ ] Use persistent browser context
- [ ] Add human-like typing delays
- [ ] Avoid headless mode (or use new headless)
- [ ] Disable automation flags in launch args
- [ ] Maintain consistent browser fingerprint
- [ ] Preserve login session across requests
- [ ] Use real browser (Edge) instead of Chromium
- [ ] Add random delays between actions
- [ ] Simulate realistic user behavior patterns

## Potential Issues and Solutions

### Issue 1: Async Context in Sync MCP Server
**Problem**: MCP server uses sync stdin/stdout, but Playwright is async

**Solution**: Use `asyncio.to_thread()` for blocking I/O and run Playwright functions with `await`

### Issue 2: Browser State Persistence
**Problem**: Need to maintain login across multiple tool calls

**Solution**: Use `storage_state()` to save/load authentication state to disk

### Issue 3: Long Response Timeouts
**Problem**: Gemini responses can take up to 1 hour

**Solution**: Set high timeouts on page operations and use JavaScript polling instead of Python-side waiting

### Issue 4: Detection Despite Stealth
**Problem**: Gemini might still detect automation

**Solution**: 
- Use non-headless mode
- Add more human-like behavior
- Consider playwright-stealth library
- Use real Edge browser channel
- Maintain consistent fingerprint

## Testing Strategy

### Unit Tests
- Browser launch and configuration
- Context creation and persistence
- JavaScript injection and execution
- Response extraction logic

### Integration Tests
- Full MCP protocol flow
- Multiple sequential requests
- Session persistence across requests
- Error handling and recovery

### Manual Tests
- Login flow (first run)
- Prompt submission and response
- Long-running response handling
- Browser state persistence
- Detection avoidance verification

## Success Criteria

1. ✅ Playwright implementation successfully automates Gemini
2. ✅ No bot detection or CAPTCHA challenges
3. ✅ Login session persists across requests
4. ✅ MCP protocol compatibility maintained
5. ✅ Long responses (1 hour) handled correctly
6. ✅ Error handling and logging preserved
7. ✅ Performance comparable or better than Selenium

## Rollout Plan

1. **Development**: Create new file alongside existing Selenium version
2. **Testing**: Validate functionality in isolated environment
3. **Comparison**: Run both versions in parallel to compare detection rates
4. **Migration**: Switch to Playwright version once validated
5. **Cleanup**: Keep Selenium version as backup initially
6. **Documentation**: Update usage instructions and configuration guide

## Additional Enhancements (Optional)

### 1. Playwright-Stealth Integration
```python
from playwright_stealth import stealth_async

async def get_page(context):
    page = await context.new_page()
    await stealth_async(page)
    return page
```

### 2. Request Interception
```python
async def route_handler(route):
    # Block analytics and tracking
    if any(x in route.request.url for x in ['analytics', 'tracking']):
        await route.abort()
    else:
        await route.continue_()

await page.route('**/*', route_handler)
```

### 3. Screenshot on Error
```python
except Exception as e:
    screenshot_path = BASE_DIR / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
    await page.screenshot(path=str(screenshot_path))
    logging.error(f"Screenshot saved to {screenshot_path}")
    raise
```

## References

- [Playwright Python Documentation](https://playwright.dev/python/)
- [Playwright Anti-Detection Guide](https://playwright.dev/docs/test-use-options#emulation)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Browser Fingerprinting Techniques](https://pixelscan.net/)

## Next Steps

Once this plan is approved:
1. Switch to Code mode to implement the solution
2. Create [`mcp_playwright.py`](../web-screper/mcp_playwright.py) with full implementation
3. Update [`requirements.txt`](../requirements.txt) with Playwright dependencies
4. Test the implementation thoroughly
5. Document usage instructions and differences
