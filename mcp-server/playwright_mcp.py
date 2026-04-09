"""
Playwright-based MCP Server for Gemini Browser Automation
Enhanced with production-grade anti-detection techniques

Based on expert recommendations from Gemini review:
- CDP-level property masking
- Telemetry blocking
- Human-like typing behavior
- Hardware fingerprint randomization
- Consistent headers and user agent
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Import configuration and stealth utilities
from config import (
    GEMINI_URL, STATE_FILE, LOG_FILE, BASE_DIR, USER_DATA_DIR,
    USE_HEADLESS, BROWSER_CHANNEL,
    BLOCK_TELEMETRY, USE_HUMAN_TYPING,
    USER_AGENT, SEC_CH_UA, SEC_CH_UA_MOBILE, SEC_CH_UA_PLATFORM,
    VIEWPORT_WIDTH, VIEWPORT_HEIGHT, LOCALE, TIMEZONE_ID,
    NAVIGATION_TIMEOUT, SCRIPT_TIMEOUT, PAGE_TIMEOUT,
    HARDWARE_CONCURRENCY, DEVICE_MEMORY
)
from stealth_utils import (
    create_stealth_page, human_type, setup_telemetry_blocking,
    apply_all_stealth_patches, random_delay
)

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),  # MCP safe
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)


def log_json(prefix, data):
    """Log JSON data with pretty formatting"""
    try:
        logger.debug(f"{prefix}: {json.dumps(data, indent=2)}")
    except:
        logger.debug(f"{prefix}: {data}")


# ---------------- BROWSER MANAGEMENT ----------------
async def get_browser():
    """
    Launch Playwright browser with anti-detection settings
    Uses Chrome's new headless mode for undetectable automation
    
    Returns:
        tuple: (playwright instance, browser instance)
    """
    logger.info(f"Launching Playwright browser... (headless={USE_HEADLESS})")
    playwright = await async_playwright().start()
    
    # Build args list - only add headless flag if USE_HEADLESS is True
    launch_args = [
        '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-sync',
            '--force-color-profile=srgb',
            '--metrics-recording-only',
            '--no-first-run',
            '--password-store=basic',
            '--use-mock-keychain',
            '--disable-extensions'
        ]
    
    # Only add headless flag if headless mode is enabled
    if USE_HEADLESS:
        launch_args.insert(0, '--headless=new')
    
    # Launch options
    launch_options = {
        'headless': USE_HEADLESS,
        'channel': BROWSER_CHANNEL,
        'args': launch_args
    }
    
    # Use persistent user data directory to maintain login across sessions
    if USER_DATA_DIR:
        logger.info(f"Using persistent profile: {USER_DATA_DIR}")
        context = await playwright.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            **launch_options,
            viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
            user_agent=USER_AGENT,
            locale=LOCALE,
            timezone_id=TIMEZONE_ID,
            extra_http_headers={
                'sec-ch-ua': SEC_CH_UA,
                'sec-ch-ua-mobile': SEC_CH_UA_MOBILE,
                'sec-ch-ua-platform': SEC_CH_UA_PLATFORM
            }
        )
        # Return context as browser for compatibility
        return playwright, context
    else:
        browser = await playwright.chromium.launch(**launch_options)
        return playwright, browser
    
    logger.info(f"Browser launched successfully (headless={USE_HEADLESS}, channel={BROWSER_CHANNEL})")
    return playwright, browser


async def get_context(browser):
    """
    Create or load persistent browser context with enhanced stealth
    If using persistent context, browser IS the context
    
    Args:
        browser: Playwright browser instance or persistent context
        
    Returns:
        BrowserContext with stealth patches applied
    """
    # If using persistent context (USER_DATA_DIR), browser is already the context
    if USER_DATA_DIR:
        logger.info("Using persistent context (already logged in)")
        context = browser
    else:
        logger.info("Creating browser context...")
        
        # Context options with consistent headers
        context_options = {
            'viewport': {'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
            'user_agent': USER_AGENT,
            'locale': LOCALE,
            'timezone_id': TIMEZONE_ID,
            'extra_http_headers': {
                'sec-ch-ua': SEC_CH_UA,
                'sec-ch-ua-mobile': SEC_CH_UA_MOBILE,
                'sec-ch-ua-platform': SEC_CH_UA_PLATFORM,
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'accept-encoding': 'gzip, deflate, br',
                'accept-language': 'en-US,en;q=0.9'
            }
        }
        
        # Load existing session if available
        if STATE_FILE.exists():
            logger.info(f"Loading existing session from {STATE_FILE}")
            context_options['storage_state'] = str(STATE_FILE)
        else:
            logger.info("No existing session found, creating new context")
        
        context = await browser.new_context(**context_options)
    
    # Apply all stealth patches
    await apply_all_stealth_patches(context)
    
    # Set timeouts
    context.set_default_timeout(PAGE_TIMEOUT)
    context.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
    
    logger.info("Browser context ready with full stealth configuration")
    return context


# ---------------- GEMINI INTERACTION ----------------
async def ask_gemini_playwright(prompt: str) -> str:
    """
    Send prompt to Gemini using Playwright with full stealth
    
    Args:
        prompt: Text prompt to send to Gemini
        
    Returns:
        str: Response from Gemini
    """
    playwright_instance = None
    browser = None
    context = None
    page = None
    
    try:
        logger.info("=== NEW GEMINI REQUEST ===")
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        # Launch browser and create context
        playwright_instance, browser = await get_browser()
        context = await get_context(browser)
        page = await create_stealth_page(context)
        
        # Block telemetry if enabled
        if BLOCK_TELEMETRY:
            await setup_telemetry_blocking(page)
        
        # Navigate to Gemini
        logger.info(f"Navigating to {GEMINI_URL}")
        # Use 'domcontentloaded' instead of 'networkidle' - Gemini has continuous network activity
        await page.goto(GEMINI_URL, wait_until='domcontentloaded', timeout=NAVIGATION_TIMEOUT)
        
        # Wait a bit for the page to fully load
        logger.info("Page loaded, waiting for UI to initialize...")
        await asyncio.sleep(5)
        
        # If not headless and no saved session, give user time to log in
        if not USE_HEADLESS and not STATE_FILE.exists():
            logger.info("=" * 60)
            logger.info("FIRST TIME LOGIN REQUIRED")
            logger.info("Please log in to Gemini in the browser window")
            logger.info("Waiting 60 seconds for manual login...")
            logger.info("=" * 60)
            await asyncio.sleep(60)
        
        # Add random delay to simulate human behavior
        await random_delay(1000, 2000)
        
        # Wait for input field
        input_selector = '[data-placeholder="Ask Gemini"]'
        logger.debug(f"Waiting for input field: {input_selector}")
        await page.wait_for_selector(input_selector, timeout=30000)
        
        # Type prompt with human-like behavior
        if USE_HUMAN_TYPING:
            logger.info("Using human-like typing behavior")
            await human_type(page, input_selector, prompt)
        else:
            logger.info("Using standard typing")
            await page.type(input_selector, prompt, delay=50)
        
        # Add small delay before pressing Enter
        await random_delay(300, 700)
        
        # Press Enter to submit
        logger.debug("Submitting prompt...")
        await page.keyboard.press('Enter')
        
        # Wait for response with polling (handles long responses up to 1 hour)
        logger.info("Waiting for Gemini response...")
        response = await page.evaluate("""
            async () => {
                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                let lastLength = 0;
                let stableCount = 0;
                let iterations = 0;
                const maxIterations = 3600; // 1 hour at 1 second intervals
                
                while (iterations < maxIterations) {
                    try {
                        const msgs = document.querySelectorAll('message-content');
                        if (msgs.length > 0) {
                            const last = msgs[msgs.length - 1].innerText;
                            const currentLength = last ? last.length : 0;
                            
                            // Check if response has stopped growing (stable for 3 checks)
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
                    } catch (e) {
                        return "JS ERROR: " + e.message;
                    }
                    
                    await sleep(1000);
                    iterations++;
                }
                
                return "TIMEOUT: Response took longer than 1 hour";
            }
        """)
        
        logger.info(f"Response received: {len(response)} characters")
        
        # Save session state for next request
        logger.debug(f"Saving session state to {STATE_FILE}")
        await context.storage_state(path=str(STATE_FILE))
        
        return response
        
    except Exception as e:
        logger.error(f"ask_gemini_playwright FAILED: {e}", exc_info=True)
        
        # Try to capture screenshot on error
        if page:
            try:
                screenshot_path = BASE_DIR / f"error_{datetime.now():%Y%m%d_%H%M%S}.png"
                await page.screenshot(path=str(screenshot_path))
                logger.error(f"Error screenshot saved to {screenshot_path}")
            except:
                pass
        
        return f"ERROR: {str(e)}"
        
    finally:
        # Clean up resources
        if page:
            try:
                await page.close()
            except Exception as e:
                logger.error(f"Error closing page: {e}")
        
        if context:
            try:
                await context.close()
            except Exception as e:
                logger.error(f"Error closing context: {e}")
        
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
        
        if playwright_instance:
            try:
                await playwright_instance.stop()
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")
        
        logger.info("=== REQUEST COMPLETE ===")


# ---------------- MCP SERVER ----------------
async def mcp_server():
    """
    MCP (Model Context Protocol) server implementation
    Handles JSON-RPC communication via stdin/stdout
    """
    logger.info("MCP server started (Playwright version)")
    
    while True:
        # Read from stdin (blocking, but in async context)
        line = await asyncio.to_thread(sys.stdin.readline)
        
        if not line:
            logger.info("STDIN closed. Shutting down.")
            break
        
        logger.debug(f"RAW INPUT: {line.strip()}")
        
        try:
            req = json.loads(line)
            log_json("REQUEST", req)
            
            req_id = req.get("id")
            method = req.get("method")
            
            response = {
                "jsonrpc": "2.0",
                "id": req_id
            }
            
            # ---------------- INITIALIZE ----------------
            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": "gemini-playwright-bridge",
                        "version": "6.0.0"
                    }
                }
            
            # ---------------- TOOLS ----------------
            elif method == "tools/list":
                response["result"] = {
                    "tools": [
                        {
                            "name": "ask_gemini",
                            "description": "Send a prompt to Gemini via Playwright browser automation with stealth",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "Prompt to send to Gemini"
                                    }
                                },
                                "required": ["prompt"]
                            }
                        }
                    ]
                }
            
            # ---------------- RESOURCES (EMPTY) ----------------
            elif method == "resources/list":
                response["result"] = {
                    "resources": []
                }
            
            elif method == "resources/templates/list":
                response["result"] = {
                    "resourceTemplates": []
                }
            
            # ---------------- PROMPTS (EMPTY) ----------------
            elif method == "prompts/list":
                response["result"] = {
                    "prompts": []
                }
            
            # ---------------- TOOL CALL ----------------
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                logger.debug(f"Tool call: {tool_name}")
                log_json("ARGS", arguments)
                
                if tool_name == "ask_gemini":
                    prompt = arguments.get("prompt", "")
                    output = await ask_gemini_playwright(prompt)
                    
                    response["result"] = {
                        "content": [
                            {
                                "type": "text",
                                "text": output
                            }
                        ]
                    }
                else:
                    response["error"] = {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
            
            # ---------------- NOTIFICATIONS ----------------
            elif req_id is None:
                # Notification, no response needed
                continue
            
            # ---------------- UNKNOWN ----------------
            else:
                # Return empty result for unknown methods
                response["result"] = {}
            
            log_json("RESPONSE", response)
            
            # Write response to stdout
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            logger.error(f"MCP ERROR: {e}", exc_info=True)
            
            err = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


# ---------------- ENTRY POINT ----------------
if __name__ == "__main__":
    try:
        asyncio.run(mcp_server())
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}))
        sys.stdout.flush()
