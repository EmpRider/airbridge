# Selenium to Playwright Conversion Plan (Updated with Gemini Expert Review)

## Overview
Convert the existing Selenium-based Gemini browser automation to use Playwright instead, with enhanced anti-detection capabilities including playwright-stealth library, new headless mode, and **production-grade hardening based on Gemini expert review**.

## Expert Review Summary
✅ **Gemini Expert Recommendation**: PROCEED with modifications
- Core plan is sound and well-architected
- Playwright is strongly recommended over Selenium
- Additional hardening required for Google's advanced detection systems
- See [`plans/gemini-expert-review.md`](gemini-expert-review.md) for full review

## Problem Statement
The current Selenium implementation is being detected as automation by Gemini, which can lead to:
- Blocked requests
- CAPTCHA challenges
- Session termination
- Degraded functionality

## Why Playwright?
Playwright offers several advantages over Selenium for avoiding detection:

1. **Better Stealth by Default**: Playwright has fewer automation fingerprints
2. **Playwright-Stealth Library**: Additional patches to remove automation indicators
3. **New Headless Mode**: Chrome's new headless mode is undetectable
4. **Native Async Support**: Better performance and resource management
5. **Built-in Context Isolation**: Cleaner session management
6. **Modern Browser APIs**: More reliable element interaction
7. **Better Network Control**: Can intercept and modify requests
8. **CDP Protocol**: Chrome DevTools Protocol is faster and less detectable than WebDriver

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

## Playwright Anti-Detection Strategy (Enhanced)

### 1. Playwright-Stealth Integration
```python
from playwright_stealth import stealth_async

# Apply stealth patches to page
async def create_stealth_page(context):
    page = await context.new_page()
    await stealth_async(page)
    return page
```

### 2. New Headless Mode (Critical)
```python
# Use Chrome's new headless mode (undetectable)
browser = await playwright.chromium.launch(
    headless=True,  # New headless mode
    channel="chrome",  # Use Chrome for best compatibility
    args=['--headless=new']  # Explicitly use new headless
)
```

### 3. CDP-Level Property Masking (NEW - Expert Recommendation)
```python
# Remove debugger traces at CDP level
await context.add_init_script("""
    // Remove Runtime.enable and Log.enable traces
    delete window.chrome.runtime;
    
    // Mask CDP detection
    Object.defineProperty(window, '__playwright', {
        get: () => undefined
    });
    
    Object.defineProperty(window, '__pw_manual', {
        get: () => undefined
    });
""")
```

### 4. Request Interception for Telemetry (NEW - Expert Recommendation)
```python
async def route_handler(route):
    """Block analytics and tracking to prevent fingerprinting"""
    blocked_domains = [
        'google-analytics.com',
        'googletagmanager.com',
        'doubleclick.net',
        'analytics.google.com',
        'stats.g.doubleclick.net'
    ]
    
    if any(domain in route.request.url for domain in blocked_domains):
        await route.abort()
    else:
        await route.continue_()

await page.route('**/*', route_handler)
```

### 5. Human-like Typing Cadence (NEW - Expert Recommendation)
```python
import random

async def human_type(page, selector, text):
    """Type with human-like variable speed and occasional corrections"""
    await page.focus(selector)
    
    for i, char in enumerate(text):
        # Variable typing speed (50-150ms)
        delay = random.randint(50, 150)
        
        # Occasional typo and correction (5% chance)
        if random.random() < 0.05 and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.type(wrong_char, delay=delay)
            await asyncio.sleep(random.randint(100, 300) / 1000)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(random.randint(50, 150) / 1000)
        
        await page.keyboard.type(char, delay=delay)
```

### 6. Hardware Fingerprint Randomization (NEW - Expert Recommendation)
```python
async def get_context(browser):
    """Create context with realistic hardware fingerprint"""
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'locale': 'en-US',
        'timezone_id': 'America/New_York',
    }
    
    if STATE_FILE.exists():
        context_options['storage_state'] = str(STATE_FILE)
    
    context = await browser.new_context(**context_options)
    
    # Hardware fingerprint randomization
    await context.add_init_script("""
        // Realistic hardware values for consumer devices
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8  // Common for modern CPUs
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8  // 8GB RAM is common
        });
        
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Consistent plugin fingerprint
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name: 'Native Client', filename: 'internal-nacl-plugin'}
            ]
        });
        
        // Consistent language
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """)
    
    return context
```

### 7. Consistent Headers (Expert Recommendation)
```python
# Ensure User-Agent matches Sec-CH-UA headers
context = await browser.new_context(
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    extra_http_headers={
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
)
```

## Architecture Changes

### New Directory Structure
```
web-scraper/                  # Fixed typo from web-screper
├── selenium_mcp.py           # Original Selenium version (renamed for clarity)
└── browser_state/            # Persistent browser context storage
    └── state.json            # Authentication state

mcp-server/                   # New generic MCP server directory
├── playwright_mcp.py         # New Playwright implementation
├── config.py                 # Configuration constants
├── stealth_utils.py          # Stealth helper functions (NEW)
└── browser_state/            # Persistent browser context storage
    └── state.json            # Authentication state
```

### Migration Path
1. Rename [`web-screper/`](../web-screper/) to [`web-scraper/`](../web-scraper/)
2. Rename [`web-scraper/mcp.py`](../web-scraper/mcp.py) to [`web-scraper/selenium_mcp.py`](../web-scraper/selenium_mcp.py)
3. Create new [`mcp-server/`](../mcp-server/) directory
4. Implement [`mcp-server/config.py`](../mcp-server/config.py)
5. Implement [`mcp-server/stealth_utils.py`](../mcp-server/stealth_utils.py) with expert-recommended functions
6. Implement [`mcp-server/playwright_mcp.py`](../mcp-server/playwright_mcp.py)

### Dependencies Update
```txt
# requirements.txt
playwright>=1.40.0
playwright-stealth>=1.0.0  # REQUIRED: Essential for anti-detection
```

### Configuration Changes
```python
# config.py - Centralized configuration
from pathlib import Path

BASE_DIR = Path.home() / "web-proxy"
BROWSER_STATE_DIR = BASE_DIR / "browser_state"
STATE_FILE = BROWSER_STATE_DIR / "state.json"
LOG_FILE = BASE_DIR / "mcp_playwright.log"

# Gemini configuration
GEMINI_URL = "https://gemini.google.com/app"

# Timeout configuration (unchanged)
SCRIPT_TIMEOUT = 3600  # 1 hour
PAGE_TIMEOUT = 3600    # 1 hour
NAVIGATION_TIMEOUT = 60000  # 60 seconds

# Browser configuration
USE_HEADLESS = True  # Use new headless mode
BROWSER_CHANNEL = "chrome"  # Use Chrome for best compatibility

# Stealth configuration (NEW)
BLOCK_TELEMETRY = True  # Block analytics and tracking
USE_HUMAN_TYPING = True  # Use human-like typing patterns
RANDOMIZE_HARDWARE = True  # Randomize hardware fingerprint
```

## Implementation Details

### 1. Browser Launch with New Headless Mode
```python
from playwright.async_api import async_playwright
from config import USE_HEADLESS, BROWSER_CHANNEL

async def get_browser():
    """Launch Playwright browser with anti-detection settings"""
    playwright = await async_playwright().start()
    
    browser = await playwright.chromium.launch(
        headless=USE_HEADLESS,  # Use new headless mode
        channel=BROWSER_CHANNEL,  # Chrome for best compatibility
        args=[
            '--headless=new',  # Explicitly use new headless engine
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
    )
    
    return playwright, browser
```

### 2. Stealth Utils Module (NEW)
```python
# stealth_utils.py - Helper functions for stealth automation
import random
import asyncio
from playwright_stealth import stealth_async

async def create_stealth_page(context):
    """Create a page with playwright-stealth applied"""
    page = await context.new_page()
    await stealth_async(page)
    return page

async def human_type(page, selector, text):
    """Type with human-like variable speed and occasional corrections"""
    await page.focus(selector)
    
    for i, char in enumerate(text):
        delay = random.randint(50, 150)
        
        # Occasional typo and correction (5% chance)
        if random.random() < 0.05 and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.type(wrong_char, delay=delay)
            await asyncio.sleep(random.randint(100, 300) / 1000)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(random.randint(50, 150) / 1000)
        
        await page.keyboard.type(char, delay=delay)

async def setup_telemetry_blocking(page):
    """Block analytics and tracking requests"""
    blocked_domains = [
        'google-analytics.com',
        'googletagmanager.com',
        'doubleclick.net',
        'analytics.google.com',
        'stats.g.doubleclick.net'
    ]
    
    async def route_handler(route):
        if any(domain in route.request.url for domain in blocked_domains):
            await route.abort()
        else:
            await route.continue_()
    
    await page.route('**/*', route_handler)
```

### 3. Context Management with Enhanced Stealth
```python
from config import STATE_FILE

async def get_context(browser):
    """Create or load persistent browser context with enhanced stealth"""
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'locale': 'en-US',
        'timezone_id': 'America/New_York',
        'extra_http_headers': {
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
    }
    
    if STATE_FILE.exists():
        context_options['storage_state'] = str(STATE_FILE)
    
    context = await browser.new_context(**context_options)
    
    # Apply comprehensive anti-detection patches
    await context.add_init_script("""
        // Hardware fingerprint
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
        
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
        
        // Remove automation indicators
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // CDP detection removal
        delete window.chrome.runtime;
        Object.defineProperty(window, '__playwright', {
            get: () => undefined
        });
        Object.defineProperty(window, '__pw_manual', {
            get: () => undefined
        });
        
        // Consistent plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                {name: 'Native Client', filename: 'internal-nacl-plugin'}
            ]
        });
        
        // Consistent languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """)
    
    return context
```

### 4. Gemini Interaction with Full Stealth
```python
from config import GEMINI_URL, NAVIGATION_TIMEOUT, STATE_FILE, USE_HUMAN_TYPING, BLOCK_TELEMETRY
from stealth_utils import create_stealth_page, human_type, setup_telemetry_blocking

async def ask_gemini_playwright(prompt: str) -> str:
    """Send prompt to Gemini using Playwright with full stealth"""
    playwright, browser = await get_browser()
    context = await get_context(browser)
    page = await create_stealth_page(context)
    
    try:
        # Block telemetry if enabled
        if BLOCK_TELEMETRY:
            await setup_telemetry_blocking(page)
        
        # Navigate to Gemini with timeout
        await page.goto(GEMINI_URL, wait_until='networkidle', timeout=NAVIGATION_TIMEOUT)
        
        # Wait for input field
        input_selector = '[data-placeholder="Ask Gemini"]'
        await page.wait_for_selector(input_selector, timeout=30000)
        
        # Type prompt with human-like behavior
        if USE_HUMAN_TYPING:
            await human_type(page, input_selector, prompt)
        else:
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

## Anti-Detection Checklist (Enhanced)

### Core Requirements
- [x] Install and integrate playwright-stealth library
- [x] Use Chrome's new headless mode (`--headless=new`)
- [x] Remove `navigator.webdriver` flag
- [x] Use real user agent strings
- [x] Set realistic viewport dimensions (1920x1080)
- [x] Enable JavaScript and cookies
- [x] Use persistent browser context with storage_state
- [x] Disable automation flags in launch args

### Expert-Recommended Enhancements (NEW)
- [x] CDP-level property masking (remove debugger traces)
- [x] Block telemetry and analytics requests
- [x] Human-like typing with variable speed and corrections
- [x] Hardware fingerprint randomization (CPU cores, RAM)
- [x] Consistent User-Agent and Sec-CH-UA headers
- [x] Mask navigator.plugins with realistic values
- [x] Mask navigator.languages consistently
- [x] Apply stealth patches to every new page

### Behavioral Patterns
- [x] Add human-like typing delays (50-150ms per character)
- [x] Occasional typos and corrections (5% chance)
- [x] Random delays between actions
- [x] Preserve login session across requests
- [x] Maintain consistent browser fingerprint

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
| Headless Mode | Old (detectable) | New (undetectable) |
| Stealth Library | Not available | playwright-stealth |
| Directory Structure | Single file | Organized modules |
| CDP-Level Control | No | Yes |

## Migration Steps

### Phase 1: Setup
1. Install Playwright: `pip install playwright playwright-stealth`
2. Install browsers: `playwright install chrome`
3. Create directory structure (web-scraper/ and mcp-server/)
4. Update requirements.txt

### Phase 2: Implementation
1. Create [`mcp-server/config.py`](../mcp-server/config.py) with configuration
2. Create [`mcp-server/stealth_utils.py`](../mcp-server/stealth_utils.py) with expert-recommended functions
3. Create [`mcp-server/playwright_mcp.py`](../mcp-server/playwright_mcp.py) with full implementation
4. Copy MCP server boilerplate from original
5. Implement Playwright browser launch with anti-detection
6. Implement persistent context management with enhanced stealth
7. Port Gemini interaction logic to Playwright
8. Add comprehensive error handling

### Phase 3: Testing
1. Test browser launch and context creation
2. Test stealth patches and fingerprint masking
3. Test telemetry blocking
4. Test human-like typing behavior
5. Test Gemini navigation and login persistence
6. Test prompt submission and response extraction
7. Test MCP protocol communication
8. Test long-running responses (timeout handling)
9. Compare detection rates with Selenium version

### Phase 4: Optimization
1. Fine-tune anti-detection parameters
2. Optimize timeout configurations
3. Add retry logic for transient failures
4. Improve logging and debugging output
5. Monitor for detection and adjust strategies

## Success Criteria

1. ✅ Playwright implementation successfully automates Gemini
2. ✅ No bot detection or CAPTCHA challenges
3. ✅ Login session persists across requests
4. ✅ MCP protocol compatibility maintained
5. ✅ Long responses (1 hour) handled correctly
6. ✅ Error handling and logging preserved
7. ✅ Performance comparable or better than Selenium
8. ✅ Expert-recommended enhancements implemented
9. ✅ Telemetry blocking functional
10. ✅ Human-like behavior patterns working

## References

- [Playwright Python Documentation](https://playwright.dev/python/)
- [Playwright-Stealth Library](https://github.com/AtuboDad/playwright_stealth)
- [Chrome New Headless Mode](https://developer.chrome.com/articles/new-headless/)
- [Playwright Anti-Detection Guide](https://playwright.dev/docs/test-use-options#emulation)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Browser Fingerprinting Techniques](https://pixelscan.net/)
- [Gemini Expert Review](gemini-expert-review.md)

## Next Steps

Once this plan is approved:
1. Rename [`web-screper/`](../web-screper/) to [`web-scraper/`](../web-scraper/)
2. Rename [`web-scraper/mcp.py`](../web-scraper/mcp.py) to [`web-scraper/selenium_mcp.py`](../web-scraper/selenium_mcp.py)
3. Create new [`mcp-server/`](../mcp-server/) directory structure
4. Implement [`mcp-server/config.py`](../mcp-server/config.py) with centralized configuration
5. Implement [`mcp-server/stealth_utils.py`](../mcp-server/stealth_utils.py) with expert-recommended functions
6. Implement [`mcp-server/playwright_mcp.py`](../mcp-server/playwright_mcp.py) with full stealth integration
7. Update [`requirements.txt`](../requirements.txt) with Playwright and playwright-stealth
8. Install Playwright browsers: `playwright install chrome`
9. Test the implementation thoroughly with new headless mode and expert enhancements
10. Document usage instructions and differences
