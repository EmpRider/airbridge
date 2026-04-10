# Ask-Gemini MCP Server Fix Plan

## Problem Analysis

### Error
```
ERROR: Binary Location Must be a String
```

### Root Cause
The error occurs when `undetected-chromedriver` tries to initialize Chrome but encounters an issue with the `binary_location` parameter. This typically happens when:

1. **Chrome path detection fails** - undetected-chromedriver can't auto-detect Chrome
2. **Version mismatch** - ChromeDriver version doesn't match Chrome version
3. **Missing binary_location parameter** - The Chrome executable path needs to be explicitly set
4. **Incorrect parameter type** - The binary_location is being passed as None or wrong type

### Current Configuration
From [`gemini-mcp/undetected_mcp.py`](../gemini-mcp/undetected_mcp.py:71-78):
```python
driver = uc.Chrome(
    options=options,
    user_data_dir=str(CHROME_PROFILE_DIR),
    version_main=None,  # Auto-detect Chrome version
    driver_executable_path=None,  # Auto-download if needed
)
```

The code is missing the `browser_executable_path` parameter which should point to Chrome.

## Solution

### Fix 1: Add Chrome Binary Path to Configuration

**File**: [`gemini-mcp/config.py`](../gemini-mcp/config.py)

Add Chrome executable path detection:
```python
import platform
from pathlib import Path

# Chrome binary location (Windows)
def get_chrome_path():
    """Auto-detect Chrome installation path"""
    if platform.system() == "Windows":
        paths = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"
        ]
        for path in paths:
            if path.exists():
                return str(path)
    elif platform.system() == "Darwin":  # macOS
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    else:  # Linux
        return "/usr/bin/google-chrome"
    return None

CHROME_BINARY_PATH = get_chrome_path()
```

### Fix 2: Update Driver Initialization

**File**: [`gemini-mcp/undetected_mcp.py`](../gemini-mcp/undetected_mcp.py:71-78)

Update the `get_driver()` function:
```python
from config import CHROME_BINARY_PATH

def get_driver():
    """Create undetected Chrome driver"""
    logger.info(f"Launching undetected Chrome (headless={USE_HEADLESS})...")
    
    # Configure Chrome options
    options = uc.ChromeOptions()
    
    # Explicitly set Chrome binary location
    if CHROME_BINARY_PATH:
        options.binary_location = CHROME_BINARY_PATH
        logger.info(f"Using Chrome at: {CHROME_BINARY_PATH}")
    
    # Set window size
    options.add_argument(f'--window-size={WINDOW_SIZE[0]},{WINDOW_SIZE[1]}')
    
    # Headless mode (if enabled)
    if USE_HEADLESS:
        options.add_argument('--headless=new')
    
    # Create driver with explicit binary path
    driver = uc.Chrome(
        options=options,
        user_data_dir=str(CHROME_PROFILE_DIR),
        version_main=None,  # Auto-detect Chrome version
        driver_executable_path=None,  # Auto-download ChromeDriver
        browser_executable_path=CHROME_BINARY_PATH  # Explicit Chrome path
    )
    
    # Set timeouts
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(IMPLICIT_WAIT)
    
    logger.info("Chrome launched successfully")
    return driver
```

### Fix 3: Add Error Handling

Add validation to ensure Chrome is found:
```python
def get_driver():
    """Create undetected Chrome driver"""
    
    # Validate Chrome installation
    if not CHROME_BINARY_PATH:
        raise RuntimeError(
            "Chrome not found. Please install Google Chrome:\n"
            "https://www.google.com/chrome/"
        )
    
    if not Path(CHROME_BINARY_PATH).exists():
        raise RuntimeError(
            f"Chrome not found at: {CHROME_BINARY_PATH}\n"
            "Please update CHROME_BINARY_PATH in config.py"
        )
    
    logger.info(f"Launching Chrome from: {CHROME_BINARY_PATH}")
    # ... rest of the code
```

## Implementation Steps

1. **Update [`config.py`](../gemini-mcp/config.py)**
   - Add `get_chrome_path()` function
   - Add `CHROME_BINARY_PATH` constant
   - Support Windows, macOS, and Linux

2. **Update [`undetected_mcp.py`](../gemini-mcp/undetected_mcp.py)**
   - Import `CHROME_BINARY_PATH`
   - Set `options.binary_location`
   - Pass `browser_executable_path` to `uc.Chrome()`
   - Add validation and error handling

3. **Test the fix**
   - Run MCP server manually
   - Send test prompt via MCP
   - Verify Chrome launches correctly
   - Check logs for errors

4. **Update documentation**
   - Add troubleshooting section
   - Document Chrome path configuration
   - Add manual override instructions

## Testing Plan

### Test 1: Manual Test
```bash
cd gemini-mcp
python undetected_mcp.py
```

Send test request:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"What is 2+2?"}}}' | python undetected_mcp.py
```

### Test 2: MCP Integration Test
Use the MCP tool from Roo:
```
mcp--ask-gemini--ask_gemini("What is the capital of France?")
```

### Test 3: Headless Mode Test
After successful login:
1. Set `USE_HEADLESS = True` in [`config.py`](../gemini-mcp/config.py)
2. Run test again
3. Verify it works without visible browser

## Expected Outcomes

✅ Chrome launches successfully
✅ No "Binary Location Must be a String" error
✅ MCP server responds to prompts
✅ Session persists across requests
✅ Works in both headed and headless modes

## Rollback Plan

If the fix doesn't work:
1. Check Chrome installation path manually
2. Try setting `CHROME_BINARY_PATH` manually in [`config.py`](../gemini-mcp/config.py)
3. Check undetected-chromedriver version: `pip show undetected-chromedriver`
4. Try upgrading: `pip install --upgrade undetected-chromedriver`

## Additional Improvements

### 1. Add Chrome Version Detection
```python
import subprocess

def get_chrome_version():
    """Get installed Chrome version"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
                capture_output=True, text=True
            )
            return result.stdout.split()[-1]
    except:
        return None
```

### 2. Add Fallback Paths
```python
CHROME_FALLBACK_PATHS = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe")
]
```

### 3. Add Configuration Override
Allow users to set custom Chrome path via environment variable:
```python
import os

CHROME_BINARY_PATH = os.getenv("CHROME_PATH") or get_chrome_path()
```

## References

- [undetected-chromedriver documentation](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
- [Selenium ChromeOptions](https://www.selenium.dev/documentation/webdriver/browsers/chrome/)
- Current implementation: [`gemini-mcp/undetected_mcp.py`](../gemini-mcp/undetected_mcp.py)
- Configuration: [`gemini-mcp/config.py`](../gemini-mcp/config.py)
