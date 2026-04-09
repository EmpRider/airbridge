"""
First-time login helper script
Uses your existing Chrome profile to log in to Gemini once
Then saves the session for the main MCP server to use
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# Configuration
GEMINI_URL = "https://gemini.google.com/app"
BASE_DIR = Path.home() / "web-proxy"
STATE_FILE = BASE_DIR / "browser_state" / "state.json"

# Ensure directory exists
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

async def login_once():
    """
    Open Gemini in a regular Chrome window for manual login
    Save the session for later use
    """
    print("=" * 60)
    print("GEMINI FIRST-TIME LOGIN HELPER")
    print("=" * 60)
    print()
    print("This will:")
    print("1. Open Chrome with your default profile")
    print("2. Navigate to Gemini")
    print("3. Wait for you to log in manually")
    print("4. Save your session for automated use")
    print()
    print("=" * 60)
    
    async with async_playwright() as p:
        # Launch Chrome with default profile (where you're already logged in)
        print("\nLaunching Chrome...")
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",  # Use your installed Chrome
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'
        )
        
        page = await context.new_page()
        
        print(f"Navigating to {GEMINI_URL}...")
        await page.goto(GEMINI_URL)
        
        print()
        print("=" * 60)
        print("PLEASE LOG IN TO GEMINI IN THE BROWSER WINDOW")
        print("=" * 60)
        print()
        print("Steps:")
        print("1. Log in with your Google account")
        print("2. Complete any 2FA if required")
        print("3. Make sure you can see the Gemini chat interface")
        print("4. Press Enter in this terminal when done")
        print()
        
        input("Press Enter after you've logged in successfully...")
        
        # Save the session
        print(f"\nSaving session to {STATE_FILE}...")
        await context.storage_state(path=str(STATE_FILE))
        
        print()
        print("=" * 60)
        print("✅ SESSION SAVED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print(f"Session saved to: {STATE_FILE}")
        print()
        print("Now you can:")
        print("1. Close this window")
        print("2. Set USE_HEADLESS=True in config.py")
        print("3. Run the main MCP server")
        print()
        print("The server will use your saved session automatically!")
        print("=" * 60)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(login_once())
