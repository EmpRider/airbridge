# undetected_mcp.py - Improvements & Error Handling Guide

## Overview
The `undetected_mcp.py` has been significantly enhanced with robust error handling, dependency validation, and CLI argument support to address common failure points.

---

## 🔧 Key Improvements

### 1. **Dependency Validation**
**Problem:** Missing packages like `undetected-chromedriver` or `selenium` would crash immediately.

**Solution:** 
- Added `check_and_install_dependencies()` that validates all required packages before importing
- Provides helpful error messages with installation commands
- Prevents cryptic import errors

```python
# Dependencies are validated before use
try:
    check_and_install_dependencies()
except ImportError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
```

**Usage:**
```bash
# Auto-install missing dependencies
python undetected_mcp.py --install-deps
```

---

### 2. **Comprehensive Chrome Detection**
**Problem:** Chrome location varies by OS and installation method; fixed paths fail silently.

**Solution:**
- `find_chrome_executable()` - Searches system PATH and common installation locations
- Multi-platform support (Windows, macOS, Linux)
- Tests multiple possible paths before failing
- Fallback to environment variable `CHROME_PATH`

**Detection Order:**
1. `--chrome-path` CLI argument
2. `CHROME_BINARY_PATH` from config.py
3. `CHROME_PATH` environment variable
4. System PATH search (google-chrome, chrome, chromium)
5. Common installation directories

---

### 3. **Robust Chrome Validation**
**Problem:** Tools fail cryptically when Chrome isn't installed.

**Solution:**
- `validate_chrome()` - Comprehensive validation with helpful error messages
- Provides installation instructions for different OS
- Suggests common installation paths

```bash
# Check if Chrome is installed
python undetected_mcp.py --check-chrome

# Output:
# ✓ Chrome found at: C:\Program Files\Google\Chrome\Application\chrome.exe
```

---

### 4. **CLI Arguments for Configuration**
**Problem:** Configuration was hardcoded or buried in config.py; difficult to override.

**Solution:** Added command-line arguments for all key settings:

```bash
# Specify Chrome path
python undetected_mcp.py --chrome-path "/path/to/chrome"

# Use headless mode
python undetected_mcp.py --headless

# Use custom profile directory
python undetected_mcp.py --profile-dir "/custom/path"

# Install dependencies
python undetected_mcp.py --install-deps

# Check Chrome installation
python undetected_mcp.py --check-chrome

# Enable verbose logging
python undetected_mcp.py --verbose
```

---

### 5. **BrowserConfig Class**
**Problem:** Browser configuration scattered across functions; difficult to manage state.

**Solution:**
- Centralized `BrowserConfig` class manages all browser settings
- Validates Chrome on initialization
- Supports CLI overrides
- Creates profile directory automatically

```python
class BrowserConfig:
    def __init__(self, chrome_path=None, headless=None, profile_dir=None):
        # Validate Chrome
        self.chrome_executable = validate_chrome(self.chrome_path)
        # Ensure directories exist
        self.profile_dir.mkdir(parents=True, exist_ok=True)
    
    def get_driver(self):
        # Create WebDriver with error handling
```

---

### 6. **Enhanced ask_gemini() Function**
**Problem:** No way to override Chrome path per request; limited error handling.

**Solution:**
- Added `chrome_path` and `headless` parameters
- Each request can use different Chrome configuration
- Specific error messages for each failure point

```python
def ask_gemini(prompt: str, chrome_path: str = None, headless: bool = None) -> str:
    """Send prompt to Gemini with optional config overrides"""
    try:
        config = get_browser_config(chrome_path, headless)
        driver = config.get_driver()
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    except RuntimeError as e:
        return f"ERROR: {e}"
```

---

### 7. **Better Logging**
**Problem:** Log file creation could fail silently; unclear error sources.

**Solution:**
- `setup_logging()` with fallback to stderr
- Logs to both file and stderr (MCP safe)
- Gracefully handles log file permission issues

```python
def setup_logging(log_file: Path = None):
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: Could not create log file: {e}", file=sys.stderr)
```

---

### 8. **MCP Tool Schema Updates**
**Problem:** Tool didn't support optional Chrome path specification.

**Solution:** Updated tool schema to include optional parameters:

```json
{
  "name": "ask_gemini",
  "inputSchema": {
    "properties": {
      "prompt": {"type": "string"},
      "chrome_path": {"type": "string", "description": "Optional: Path to Chrome"},
      "headless": {"type": "boolean", "description": "Optional: Headless mode"}
    },
    "required": ["prompt"]
  }
}
```

---

## 📋 Common Failing Points - RESOLVED

| Issue | Before | After |
|-------|--------|-------|
| Chrome not installed | Cryptic crash | Auto-detects, suggests installation |
| Dependencies missing | ImportError crash | Validates, provides install commands |
| Chrome path wrong | Silent failure | Validates path, provides alternatives |
| Log file can't be created | Crash | Falls back to stderr, warns user |
| Per-request config needed | Impossible | Supports via CLI args and MCP params |
| Unknown Chrome location on CI/Docker | Fails on start | Uses --check-chrome or --chrome-path |

---

## 🚀 Usage Examples

### Example 1: Basic MCP Server Start
```bash
cd gemini-mcp
python undetected_mcp.py
```

### Example 2: Specify Chrome Path
```bash
# If Chrome is in non-standard location
python undetected_mcp.py --chrome-path "/usr/bin/google-chrome-stable"
```

### Example 3: Docker/CI Environment
```bash
# Install dependencies first
python undetected_mcp.py --install-deps

# Check if Chrome is available
python undetected_mcp.py --check-chrome

# Start with explicit path
python undetected_mcp.py --chrome-path "/snap/bin/chromium"
```

### Example 4: Verify Setup
```bash
# Quick verification script
python -c "from undetected_mcp import *; validate_chrome(); print('✓ Setup OK')"
```

---

## 🔍 Troubleshooting

### Problem: "Chrome not found"
**Solution 1:** Install Chrome
```bash
# Windows
# Download from https://www.google.com/chrome/

# macOS
# brew install google-chrome

# Linux
# sudo apt-get install google-chrome-stable
```

**Solution 2:** Specify Chrome path
```bash
python undetected_mcp.py --chrome-path "/path/to/chrome"
```

**Solution 3:** Check where Chrome is
```bash
python undetected_mcp.py --check-chrome
```

---

### Problem: "Missing required packages"
**Solution:**
```bash
# Install all dependencies
python undetected_mcp.py --install-deps

# Or manually
pip install undetected-chromedriver selenium setuptools
```

---

### Problem: Permission denied for log file
**Solution:** The script automatically falls back to stderr. Log output will be printed but not saved. To fix:
```bash
# Ensure directory is writable
mkdir -p ~/web-proxy
chmod 755 ~/web-proxy
```

---

### Problem: "ChromeDriver creation failed"
**Solution:**
1. Check Chrome is installed: `python undetected_mcp.py --check-chrome`
2. Try updating undetected-chromedriver:
```bash
pip install --upgrade undetected-chromedriver
```
3. Check Chrome version matches:
```bash
chrome --version
pip show undetected-chromedriver
```

---

## 📊 Configuration Priority

Settings are resolved in this order (first match wins):

1. **CLI Arguments** (highest priority)
   ```bash
   python undetected_mcp.py --chrome-path /custom/path
   ```

2. **MCP Tool Arguments** (for ask_gemini calls)
   ```json
   {"arguments": {"prompt": "...", "chrome_path": "/custom/path"}}
   ```

3. **Environment Variables**
   ```bash
   export CHROME_PATH=/custom/path
   ```

4. **config.py Defaults** (lowest priority)
   ```python
   CHROME_BINARY_PATH = os.getenv("CHROME_PATH") or get_chrome_path()
   ```

---

## ✅ Verification Checklist

Run these to verify everything is working:

```bash
# 1. Check dependencies
python undetected_mcp.py --install-deps

# 2. Verify Chrome
python undetected_mcp.py --check-chrome

# 3. Test import
python -c "import undetected_chromedriver; print('✓ Import OK')"

# 4. View help
python undetected_mcp.py --help

# 5. Start server
python undetected_mcp.py
```

---

## 🎯 Next Steps

1. **Initial Setup:**
   ```bash
   python undetected_mcp.py --install-deps
   python undetected_mcp.py --check-chrome
   ```

2. **Integration:**
   - Pass `--chrome-path` from your deployment/CI environment
   - Use MCP tool schema with optional chrome_path parameter
   - Monitor logs for specific failure reasons

3. **Customization:**
   - Override via CLI: `python undetected_mcp.py --chrome-path "..." --headless`
   - Or via config.py: Edit `CHROME_BINARY_PATH`, `USE_HEADLESS`, etc.

---

## 📚 Reference

### New Command-Line Options
- `--chrome-path PATH` - Specify Chrome executable location
- `--headless` - Run in headless mode
- `--no-headless` - Run in windowed mode
- `--profile-dir PATH` - Custom Chrome profile directory
- `--check-chrome` - Verify Chrome installation and exit
- `--install-deps` - Install/upgrade dependencies and exit
- `--verbose` - Enable verbose logging
- `--help` - Show help message

### New Functions
- `check_and_install_dependencies()` - Validate required packages
- `find_chrome_executable()` - Search for Chrome installation
- `validate_chrome(path)` - Validate Chrome path with detailed errors
- `setup_logging(path)` - Initialize logging with fallbacks
- `install_dependencies()` - Install/upgrade packages
- `parse_args()` - Parse CLI arguments

### Modified Functions
- `ask_gemini(prompt, chrome_path, headless)` - Added optional overrides
- `get_driver()` → `BrowserConfig.get_driver()` - Moved to class
- `mcp_server()` - Updated to use BrowserConfig

---

**Updated:** 2024  
**Compatibility:** Python 3.8+  
**Status:** Production Ready ✓
