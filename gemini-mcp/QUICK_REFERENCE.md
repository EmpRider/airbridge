# undetected_mcp.py - Quick Reference

## ⚡ Quick Start

```bash
# 1. Install dependencies
python undetected_mcp.py --install-deps

# 2. Verify Chrome
python undetected_mcp.py --check-chrome

# 3. Start MCP server
python undetected_mcp.py
```

## 🛠️ Common Commands

```bash
# Auto-detect Chrome and start
python undetected_mcp.py

# Specify Chrome path
python undetected_mcp.py --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"

# Use headless mode
python undetected_mcp.py --headless

# Custom profile directory
python undetected_mcp.py --profile-dir "C:\Custom\Chrome\Profile"

# Install or upgrade dependencies
python undetected_mcp.py --install-deps

# Check Chrome installation
python undetected_mcp.py --check-chrome

# Show help
python undetected_mcp.py --help

# Verbose logging
python undetected_mcp.py --verbose
```

## ⚠️ Common Issues & Fixes

| Error | Quick Fix |
|-------|-----------|
| **Chrome not found** | `python undetected_mcp.py --chrome-path "/path/to/chrome"` |
| **Missing dependencies** | `python undetected_mcp.py --install-deps` |
| **Import error** | Check `config.py` and `utils.py` exist in same directory |
| **Permission denied (logs)** | Ensure `~/web-proxy` directory is writable |
| **ChromeDriver version mismatch** | `pip install --upgrade undetected-chromedriver` |

## 🔍 Troubleshooting Guide

**Step 1:** Check Chrome installation
```bash
python undetected_mcp.py --check-chrome
```
Expected output: `✓ Chrome found at: [path]`

**Step 2:** Verify dependencies
```bash
python -c "import undetected_chromedriver; import selenium; print('OK')"
```

**Step 3:** Check specific Chrome path
```bash
python undetected_mcp.py --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

**Step 4:** View logs
```bash
cat ~/web-proxy/gemini_mcp.log  # Linux/macOS
type %USERPROFILE%\web-proxy\gemini_mcp.log  # Windows
```

## 📦 Environment Variables

```bash
# Set Chrome path
export CHROME_PATH="/path/to/chrome"

# Or Windows
set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

## 🎯 MCP Tool Usage

**Tool:** `ask_gemini`

**Parameters:**
- `prompt` (required): Question/instruction for Gemini
- `chrome_path` (optional): Override Chrome location
- `headless` (optional): Force headless mode true/false

**Example:**
```json
{
  "prompt": "What is Python?",
  "chrome_path": "/usr/bin/google-chrome",
  "headless": true
}
```

## ✅ Verification Commands

```bash
# Check syntax
python -m py_compile undetected_mcp.py

# Check imports
python -c "from undetected_mcp import *; print('All imports OK')"

# Verify Chrome detection
python undetected_mcp.py --check-chrome

# Verify dependencies
python undetected_mcp.py --install-deps
```

## 📊 File Structure

```
gemini-mcp/
├── undetected_mcp.py      # Main MCP server (enhanced)
├── config.py              # Configuration (auto-detects Chrome)
├── utils.py               # Utility functions
├── IMPROVEMENTS.md        # Detailed improvements guide
├── TESTING.md             # Testing guide
└── README.md              # Original readme
```

## 🚀 Platform-Specific Chrome Paths

**Windows:**
```
C:\Program Files\Google\Chrome\Application\chrome.exe
C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
```

**macOS:**
```
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```

**Linux:**
```
/usr/bin/google-chrome
/usr/bin/google-chrome-stable
/usr/bin/chromium
/snap/bin/chromium
```

## 📝 Notes

- **Auto-detection:** Searches system PATH + common paths automatically
- **Dependency checking:** Validates packages on startup with helpful messages
- **Error handling:** Each failure point has specific, actionable error messages
- **Logging:** Falls back to stderr if log file can't be created
- **CLI overrides:** Command-line args override config.py and environment variables
