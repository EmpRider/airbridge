"""
Stealth utilities for Playwright-based browser automation
Implements expert-recommended anti-detection techniques
"""
import random
import asyncio
import logging
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)


async def create_stealth_page(context):
    """
    Create a page with playwright-stealth applied
    
    Args:
        context: Playwright browser context
        
    Returns:
        Page with stealth patches applied
    """
    page = await context.new_page()
    
    # Apply stealth patches using Stealth.apply_stealth_async()
    stealth_config = Stealth()
    await stealth_config.apply_stealth_async(page)
    
    logger.debug("Stealth patches applied to new page")
    return page


async def human_type(page, selector, text):
    """
    Type with human-like variable speed and occasional corrections
    Expert recommendation: Variable typing speed (50-150ms) with 5% typo rate
    
    Args:
        page: Playwright page object
        selector: CSS selector for input element
        text: Text to type
    """
    await page.focus(selector)
    logger.debug(f"Starting human-like typing for {len(text)} characters")
    
    for i, char in enumerate(text):
        # Variable typing speed (50-150ms per character)
        delay = random.randint(50, 150)
        
        # Occasional typo and correction (5% chance)
        if random.random() < 0.05 and i > 0:
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            await page.keyboard.type(wrong_char, delay=delay)
            await asyncio.sleep(random.randint(100, 300) / 1000)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(random.randint(50, 150) / 1000)
            logger.debug(f"Simulated typo at position {i}")
        
        await page.keyboard.type(char, delay=delay)
    
    logger.debug("Human-like typing completed")


async def setup_telemetry_blocking(page):
    """
    Block analytics and tracking requests
    Expert recommendation: Prevent Google from collecting diagnostic data
    
    Args:
        page: Playwright page object
    """
    blocked_domains = [
        'google-analytics.com',
        'googletagmanager.com',
        'doubleclick.net',
        'analytics.google.com',
        'stats.g.doubleclick.net',
        'www.google-analytics.com',
        'ssl.google-analytics.com'
    ]
    
    async def route_handler(route):
        url = route.request.url
        if any(domain in url for domain in blocked_domains):
            logger.debug(f"Blocked telemetry request: {url}")
            await route.abort()
        else:
            await route.continue_()
    
    await page.route('**/*', route_handler)
    logger.info(f"Telemetry blocking enabled for {len(blocked_domains)} domains")


async def apply_cdp_stealth(context):
    """
    Apply CDP-level property masking to remove debugger traces
    Expert recommendation: Remove Runtime.enable and Log.enable traces
    
    Args:
        context: Playwright browser context
    """
    await context.add_init_script("""
        // Remove CDP detection traces
        delete window.chrome.runtime;
        
        // Remove Playwright detection
        Object.defineProperty(window, '__playwright', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__pw_manual', {
            get: () => undefined
        });
        
        // Remove other automation indicators
        Object.defineProperty(window, '__webdriver_script_fn', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__driver_evaluate', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__webdriver_evaluate', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__selenium_evaluate', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__fxdriver_evaluate', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__driver_unwrapped', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__webdriver_unwrapped', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__selenium_unwrapped', {
            get: () => undefined
        });
        
        Object.defineProperty(window, '__fxdriver_unwrapped', {
            get: () => undefined
        });
    """)
    logger.debug("CDP-level stealth patches applied")


async def apply_hardware_fingerprint(context, hardware_concurrency=8, device_memory=8):
    """
    Apply hardware fingerprint randomization
    Expert recommendation: Use realistic consumer hardware values
    
    Args:
        context: Playwright browser context
        hardware_concurrency: Number of CPU cores (default: 8)
        device_memory: RAM in GB (default: 8)
    """
    await context.add_init_script(f"""
        // Hardware fingerprint
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {hardware_concurrency}
        }});
        
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {device_memory}
        }});
    """)
    logger.debug(f"Hardware fingerprint set: {hardware_concurrency} cores, {device_memory}GB RAM")


async def apply_navigator_overrides(context):
    """
    Apply navigator property overrides for consistent fingerprint
    
    Args:
        context: Playwright browser context
    """
    await context.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Consistent plugins (realistic Chrome plugins)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {
                    name: 'Chrome PDF Plugin',
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format',
                    length: 1
                },
                {
                    name: 'Chrome PDF Viewer',
                    filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                    description: '',
                    length: 1
                },
                {
                    name: 'Native Client',
                    filename: 'internal-nacl-plugin',
                    description: '',
                    length: 2
                }
            ]
        });
        
        // Consistent languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Consistent platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Consistent vendor
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.'
        });
    """)
    logger.debug("Navigator overrides applied")


async def apply_all_stealth_patches(context):
    """
    Apply all stealth patches to a browser context
    Combines all expert-recommended techniques
    
    Args:
        context: Playwright browser context
    """
    logger.info("Applying comprehensive stealth patches...")
    
    # Apply all patches
    await apply_cdp_stealth(context)
    await apply_hardware_fingerprint(context)
    await apply_navigator_overrides(context)
    
    logger.info("All stealth patches applied successfully")


async def random_delay(min_ms=100, max_ms=500):
    """
    Add a random delay to simulate human behavior
    
    Args:
        min_ms: Minimum delay in milliseconds
        max_ms: Maximum delay in milliseconds
    """
    delay = random.randint(min_ms, max_ms) / 1000
    await asyncio.sleep(delay)
