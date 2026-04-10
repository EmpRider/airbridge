"""
First-time login helper script for undetected-chromedriver
Uses your existing Chrome profile to log in to Gemini once
Then saves the session within the profile for the main MCP server to use
"""
import sys
from pathlib import Path

def login_once():
    """
    Open Gemini in a regular Chrome window for manual login
    """
    print("=" * 60)
    print("GEMINI FIRST-TIME LOGIN HELPER (UNDETECTED-CHROMEDRIVER)")
    print("=" * 60)
    print()
    print("This will:")
    print("1. Open Chrome with your undetected profile")
    print("2. Navigate to Gemini")
    print("3. Wait for you to log in manually")
    print("4. Persist your session for automated use")
    print()
    print("=" * 60)
    
    # Import config
    try:
        from config import GEMINI_URL, CHROME_PROFILE_DIR, WINDOW_SIZE, CHROME_BINARY_PATH
    except ImportError as e:
        print(f"ERROR: Failed to import config: {e}", file=sys.stderr)
        print("Run this script from inside the gemini-mcp directory.", file=sys.stderr)
        sys.exit(1)

    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("ERROR: undetected-chromedriver is missing. Run: pip install undetected-chromedriver", file=sys.stderr)
        sys.exit(1)

    # Validate chrome
    try:
        from undetected_mcp import validate_chrome
        chrome_exe = validate_chrome(CHROME_BINARY_PATH)
    except Exception as e:
        print(f"Warning/Error finding Chrome: {e}. Will let undetected_chromedriver auto-detect.", file=sys.stderr)
        chrome_exe = CHROME_BINARY_PATH

    print("\nLaunching Chrome...")
    options = uc.ChromeOptions()
    if chrome_exe:
        options.binary_location = chrome_exe
    
    options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')
    options.add_argument('--disable-blink-features=AutomationControlled')

    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        driver = uc.Chrome(
            options=options,
            user_data_dir=str(CHROME_PROFILE_DIR),
            version_main=None,
            driver_executable_path=None,
            browser_executable_path=chrome_exe if chrome_exe else None
        )
    except Exception as e:
        print(f"Failed to launch browser: {e}")
        print("Make sure you don't have another Chrome instance using this profile open (like the MCP server itself).")
        sys.exit(1)

    print(f"Navigating to {GEMINI_URL}...")
    driver.get(GEMINI_URL)
    
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
    
    # Session is automatically saved in user_data_dir by Chrome
    print()
    print("=" * 60)
    print("✅ SESSION SAVED SUCCESSFULLY!")
    print("=" * 60)
    print()
    print(f"Session saved to your Chrome profile: {CHROME_PROFILE_DIR}")
    print()
    print("Now you can:")
    print("1. Set USE_HEADLESS=True in config.py (if you want the server to run hidden)")
    print("2. Run the main undetected MCP server")
    print()
    print("=" * 60)
    
    driver.quit()

if __name__ == "__main__":
    login_once()
