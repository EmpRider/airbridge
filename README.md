# Gemini MCP Server

MCP (Model Context Protocol) server for Gemini automation using **undetected-chromedriver** to bypass bot detection.

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. First run (browser will open for login)
cd gemini-mcp
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"test"}}}' | python undetected_mcp.py

# 3. Log in manually in the browser window

# 4. Enable headless mode in config.py
# USE_HEADLESS = True

# 5. Use the server
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ask_gemini","arguments":{"prompt":"What is 2+2?"}}}' | python undetected_mcp.py
```

## 📁 Project Structure

```
web-chat/
├── gemini-mcp/              # 🆕 Production implementation
│   ├── undetected_mcp.py   # Main MCP server
│   ├── config.py            # Configuration
│   ├── utils.py             # Helper functions
│   └── README.md            # Documentation
│
├── archive/                 # Old implementations (backup)
│   ├── playwright/          # Playwright attempt
│   └── selenium/            # Original Selenium
│
├── docs/                    # Documentation
│   ├── plans/               # Architecture plans
│   ├── INSTALLATION.md
│   ├── QUICKSTART.md
│   └── IMPLEMENTATION_SUMMARY.md
│
└── requirements.txt         # Dependencies
```

## ✨ Features

- ✅ **No Bot Detection** - Uses undetected-chromedriver
- ✅ **Auto-Patching** - Automatically patches ChromeDriver
- ✅ **Session Persistence** - Login saved across requests
- ✅ **Human-like Typing** - Variable speed with typos
- ✅ **Simple Code** - 250 lines vs 500+ with Playwright
- ✅ **MCP Compatible** - Full protocol support

## 📖 Documentation

- **Main Guide**: [`gemini-mcp/README.md`](gemini-mcp/README.md)
- **Installation**: [`docs/INSTALLATION.md`](docs/INSTALLATION.md)
- **Quick Start**: [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- **Architecture**: [`docs/plans/`](docs/plans/)

## 🔧 Configuration

Edit [`gemini-mcp/config.py`](gemini-mcp/config.py):

```python
USE_HEADLESS = False  # False for first login, True for production
USE_HUMAN_TYPING = True  # Human-like typing behavior
```

## 🎯 MCP Integration

Add to your MCP settings:

```json
{
  "mcpServers": {
    "gemini": {
      "command": "python",
      "args": ["d:/web-chat/gemini-mcp/undetected_mcp.py"]
    }
  }
}
```

## 📊 Comparison

| Feature | Playwright | Undetected-ChromeDriver |
|---------|-----------|------------------------|
| Detection | High ❌ | Very Low ✅ |
| Code | 500+ lines | 250 lines ✅ |
| Setup | Complex | Simple ✅ |
| Google Services | Blocked ❌ | Works ✅ |

## 🛠️ Troubleshooting

See [`gemini-mcp/README.md`](gemini-mcp/README.md) for detailed troubleshooting.

## 📝 Version

**Current**: 1.0.0 (Undetected-ChromeDriver)
**Previous**: Playwright (archived)

## 📄 License

MIT
