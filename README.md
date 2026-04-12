# MCP Adapter Server

A high-concurrency, extensible **Model Context Protocol (MCP)** server that bridges AI coding assistants with browser-automated LLM interfaces. It allows tools like **Claude Code**, **VS Code Copilot**, **Cline**, **Cursor**, and any MCP-compatible client to route prompts through real browser sessions to services like Google Gemini — complete with login persistence, session management, and a pooled browser backend.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
  - [Server Settings](#server-settings)
  - [Browser Pool Settings](#browser-pool-settings)
  - [Task Configuration](#task-configuration)
  - [Selector Reference](#selector-reference)
  - [Login Configuration](#login-configuration)
- [MCP Protocol & Tools](#mcp-protocol--tools)
  - [JSON-RPC Interface](#json-rpc-interface)
  - [Available MCP Tools](#available-mcp-tools)
- [HTTP API Reference](#http-api-reference)
- [Configuring MCP for AI Tools](#configuring-mcp-for-ai-tools)
  - [Claude Desktop](#claude-desktop)
  - [Claude Code (CLI)](#claude-code-cli)
  - [VS Code (Copilot / MCP Extension)](#vs-code-copilot--mcp-extension)
  - [Cline](#cline)
  - [Cursor](#cursor)
  - [Any MCP-Compatible Client](#any-mcp-compatible-client)
- [Adding a New Adapter](#adding-a-new-adapter)
  - [Step 1: Create the Adapter File](#step-1-create-the-adapter-file)
  - [Step 2: Register the Adapter](#step-2-register-the-adapter)
  - [Step 3: Add Task Configuration](#step-3-add-task-configuration)
  - [BaseAdapter Interface Reference](#baseadapter-interface-reference)
- [Session Management](#session-management)
- [Browser Pool Internals](#browser-pool-internals)
- [Login & Authentication Flow](#login--authentication-flow)
- [Error Handling & Recovery](#error-handling--recovery)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                    AI Tools (IDE / CLI / Desktop)                      │
│          Claude Code, VS Code, Cline, Cursor, Claude Desktop          │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  JSON-RPC 2.0 (stdin/stdout)
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     MCP Client  (mcp_client.py)                       │
│  - Reads JSON-RPC from stdin, writes responses to stdout              │
│  - Auto-starts HTTP server if not running                             │
│  - Registers unique client_id per IDE instance                        │
│  - Forwards tool calls to HTTP server via httpx                       │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  HTTP/1.1 (localhost)
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     HTTP Server  (http_server.py)                      │
│  - FastAPI application with CORS (localhost only)                     │
│  - REST endpoints for queries, sessions, health, stats                │
│  - Client registration & graceful shutdown coordination               │
└────────────┬─────────────────────────────────────┬────────────────────┘
             │                                     │
             ▼                                     ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│     Browser Pool         │         │    Session Manager        │
│  (browser_pool.py)       │         │  (session_manager.py)     │
│                          │         │                          │
│  - Manages Playwright    │         │  - Multi-turn sessions   │
│    browser contexts      │         │  - Dedicated browser     │
│  - Lazy/eager spawning   │         │    slots per session     │
│  - Idle cleanup loop     │         │  - Per-session locks     │
│  - Profile-based auth    │         │  - Auto-reap idle (15m)  │
└────────────┬─────────────┘         └────────────┬─────────────┘
             │                                     │
             └──────────────┬──────────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    Adapter Factory  (adapter_factory.py)               │
│  - Reads config.json to map task names → adapter classes              │
│  - Registry pattern: register_adapter("gemini", GeminiAdapter)        │
│  - create_adapter("thinking") → GeminiAdapter instance                │
└──────────────────────────────┬────────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          ┌──────────────────┐   ┌──────────────────┐
          │  GeminiAdapter   │   │  YourAdapter      │
          │  (built-in)      │   │  (you add this)   │
          └────────┬─────────┘   └────────┬─────────┘
                   │                      │
                   └──────────┬───────────┘
                              ▼
                   ┌─────────────────────┐
                   │  Playwright Browser  │
                   │  (Chromium contexts) │
                   └─────────────────────┘
```

### Key Design Decisions

- **Client-Server Split**: The MCP client (stdin/stdout) is a thin proxy. All heavy lifting happens in the HTTP server, enabling multiple IDE instances to share one browser pool.
- **Adapter Factory Pattern**: Tasks map to adapters via `config.json`, making it possible to add new LLM targets without touching core code.
- **Browser Context Pooling**: Playwright contexts are recycled, not browser processes. Each context is isolated with its own cookies and storage.
- **Golden Profile Login**: A persistent "golden" Chrome profile stores login cookies. New contexts copy from this profile, avoiding repeated logins.
- **Dedicated Session Slots**: Multi-turn sessions get their own browser context, preventing interference with one-shot queries.

---

## How It Works

1. An AI tool (e.g., Claude Code) spawns `python main.py` as a subprocess with stdin/stdout pipes.
2. The MCP client auto-starts the HTTP server (if not already running) and registers itself.
3. The AI tool sends JSON-RPC requests (`tools/list`, `tools/call`) over stdin.
4. The MCP client forwards these as HTTP requests to the server.
5. The server acquires a browser context from the pool, creates the appropriate adapter, and runs the prompt through the real browser UI (e.g., Gemini).
6. The LLM response is extracted from the browser page and returned through the chain.
7. When the AI tool exits, the client unregisters. When the last client disconnects, the server shuts down after a grace period.

---

## Project Structure

```
web-chat/
├── main.py                              # Entry point (dual-mode: server or client)
├── requirements.txt                     # Python dependencies
├── config.json.example                  # Example configuration template
├── README.md                            # This file
│
└── mcp_manager/                         # Core package
    ├── __init__.py
    ├── server.py                        # Standalone MCP JSON-RPC stdio loop (legacy)
    ├── mcp_client.py                    # MCP client — thin JSON-RPC → HTTP proxy
    ├── http_server.py                   # FastAPI HTTP server with all REST endpoints
    ├── server_manager.py                # Server lifecycle: start, stop, PID management
    ├── browser.py                       # Browser config, Chrome discovery, profile mgmt
    ├── browser_pool.py                  # Async browser context pool (Playwright)
    ├── session_manager.py               # Multi-turn chat session management
    ├── login_handler.py                 # Interactive login flow & cookie transfer
    ├── utils.py                         # Shared utilities (typing simulation, waits)
    ├── config.json                      # Active configuration (copy from .example)
    │
    └── adapters/                        # Adapter implementations
        ├── __init__.py
        ├── base_adapter.py              # Abstract base class — the adapter contract
        ├── adapter_factory.py           # Dynamic adapter registry & creation
        └── gemini/                      # Google Gemini adapter
            ├── __init__.py
            └── gemini_adapter.py        # Concrete Gemini browser automation
```

---

## Prerequisites

- **Python 3.10+**
- **Playwright** with Chromium browser binaries
- **Google Chrome or Chromium** (optional — Playwright's bundled Chromium works)
- A logged-in account on the target LLM service (e.g., Google account for Gemini)

---

## Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd web-chat

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser binaries
playwright install chromium

# 4. Copy the example config
cp config.json.example mcp_manager/config.json

# 5. (Optional) First-run login — start in windowed mode to sign in
python main.py --server --no-headless
```

On first run with a service requiring login (like Gemini), a visible browser window will open for you to sign in manually. Your session cookies are saved to a "golden profile" at `~/.web-proxy/playwright-profiles/_golden/` and reused for subsequent runs.

---

## Quick Start

### Start the HTTP Server Directly

```bash
python main.py --server
```

### Start as MCP Client (for IDE Integration)

```bash
# The client auto-starts the server if needed
python main.py
```

### Start with Custom Settings

```bash
# Windowed mode, 4 browser slots, custom Chrome
python main.py --server --no-headless --max-browsers 4 --chrome-path /usr/bin/google-chrome
```

---

## CLI Reference

All arguments are passed to `main.py`. In client mode, relevant arguments are forwarded to the auto-started server process.

### Execution Mode

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--server` | flag | `false` | Run as HTTP server. Without this flag, runs as MCP JSON-RPC client. |

### Server Network Settings

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--host` | string | `127.0.0.1` | IP address the HTTP server binds to. |
| `--port` | int | `8765` | Port the HTTP server listens on. |
| `--pid-file` | string | `~/.web-proxy/server.pid` | Path to the PID file for server lifecycle management. Used to detect if a server is already running. |
| `--log-file` | string | `~/.web-proxy/server.log` | Path to the log file. All logs go to stderr + this file (stdout is reserved for JSON-RPC in client mode). |

### Browser Pool Settings

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--max-browsers` | int | `2` | Maximum number of concurrent Playwright browser contexts in the pool. Each context is an isolated browser session. Higher values allow more concurrent requests but use more memory. |
| `--max-tabs-per-browser` | int | `5` | **Deprecated.** Previously controlled tabs-per-browser; now ignored (contexts don't share tabs). |
| `--tab-idle-timeout` | int | `300` | **Deprecated.** Previously controlled per-tab idle timeout; now ignored. |
| `--browser-idle-timeout` | int | `1800` | Seconds of inactivity before an idle browser context is reaped by the cleanup loop. Set to `0` to disable auto-cleanup. |
| `--no-lazy-spawn` | flag | `false` | Spawn all browser contexts immediately at startup instead of on-demand. Useful for pre-warming but increases startup time. |
| `--enable-images` | flag | `false` | Allow image loading in browser contexts. Disabled by default to save bandwidth and speed up page loads. |
| `--enable-fonts` | flag | `false` | Allow font loading in browser contexts. Disabled by default for performance. |

### Browser Settings

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--chrome-path` | string | auto-detect | Path to a Chrome/Chromium executable. If not set, Playwright uses its bundled Chromium. |
| `--no-headless` | flag | `false` | Run browsers in windowed (visible) mode instead of headless. Required for first-time login. Useful for debugging. |
| `--no-temp-chat` | flag | `false` | Disable temporary/ephemeral chat mode. By default, the system enables temp chat to avoid polluting chat history. |
| `--profile-dir` | string | `~/.web-proxy/playwright-profiles` | Base directory for Chrome profiles. Contains the golden profile and per-context pool profiles. |
| `--config` | string | `mcp_manager/config.json` | Path to the task configuration JSON file. |

### Argument Forwarding (Client → Server)

When running in client mode (no `--server` flag), the client auto-starts a server subprocess. These arguments are forwarded:

```bash
# Client command:
python main.py --no-headless --max-browsers 4 --chrome-path /usr/bin/google-chrome

# Internally starts server as:
python main.py --server --no-headless --max-browsers 4 --chrome-path /usr/bin/google-chrome
```

If a server is already running with different settings, the client logs a mismatch warning but continues (e.g., `--no-headless` is ignored if the server was started headless).

---

## Configuration

The server reads its task definitions from `mcp_manager/config.json`. Copy `config.json.example` to get started.

### Server Settings

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8765,
    "auto_start": true,
    "pid_file": "~/.web-proxy/server.pid",
    "log_file": "~/.web-proxy/server.log",
    "client_idle_timeout": 300
  }
}
```

| Field | Description |
|-------|-------------|
| `host` | Bind address for the HTTP server. |
| `port` | Listen port. |
| `auto_start` | Whether the MCP client should auto-start the server. |
| `pid_file` | PID file path for process lifecycle management. |
| `log_file` | Log file path. |
| `client_idle_timeout` | Seconds after last client disconnects before server shuts down. |

### Browser Pool Settings

```json
{
  "browser_pool": {
    "max_browsers": 2,
    "browser_idle_timeout": 1800,
    "enable_image_loading": false,
    "enable_font_loading": false,
    "lazy_browser_spawn": true
  }
}
```

| Field | Description |
|-------|-------------|
| `max_browsers` | Maximum concurrent browser contexts. |
| `browser_idle_timeout` | Seconds before idle contexts are reaped. |
| `enable_image_loading` | Load images in browser pages. |
| `enable_font_loading` | Load fonts in browser pages. |
| `lazy_browser_spawn` | Spawn contexts on-demand vs. at startup. |

### Task Configuration

Each task under the `"task"` key defines a target LLM service. The task name (e.g., `"thinking"`) is what MCP clients use to route prompts.

```json
{
  "task": {
    "thinking": {
      "adapter": "gemini",
      "description": "Deep reasoning via Google Gemini",
      "url": "https://gemini.google.com/app",
      "models": ["Fast", "Thinking", "Pro"],
      "login": { ... },
      "selectors": { ... }
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `adapter` | string | Name of the registered adapter class (e.g., `"gemini"`). Must match a call to `register_adapter()`. |
| `description` | string | Human-readable description shown to AI tools via `get_available_tasks`. |
| `url` | string | The target URL the adapter navigates to (e.g., `https://gemini.google.com/app`). |
| `models` | array | List of supported model variant names. Exposed in the MCP tool schema as an enum. |
| `login` | object | Login configuration (see below). Optional — omit if the service doesn't require auth. |
| `selectors` | object | CSS selectors for browser automation (see below). |

### Selector Reference

Selectors tell the adapter how to interact with the target web application. Each key maps to an array of CSS selectors tried in order (fallback chain).

```json
{
  "selectors": {
    "temp-chat": ["button[aria-label=\"Temporary chat\"]"],
    "message-box": [
      "[data-placeholder=\"Ask Gemini\"]",
      "div[contenteditable=\"true\"]",
      ".ql-editor"
    ],
    "response-container": ["message-content"],
    "response-complete": ["message-actions"],
    "mode-picker": ["[aria-label=\"Open mode picker\"]"],
    "mode-item": ["[mat-menu-item]"],
    "sign-in": ["a[aria-label=\"Sign in\"]"]
  }
}
```

| Selector Key | Purpose |
|-------------|---------|
| `temp-chat` | Button to toggle temporary/ephemeral chat mode. Checked for `aria-pressed="true"` to avoid double-toggle. |
| `message-box` | The input field where prompts are typed. The adapter uses `keyboard.insertText()` for fast input. |
| `response-container` | The element(s) containing the LLM's response text. The adapter extracts `.innerText` from the last match. |
| `response-complete` | Element(s) that appear when the LLM finishes generating. The adapter waits for the count of these elements to increase. |
| `mode-picker` | Button/dropdown to open the model selection menu. |
| `mode-item` | Individual model options within the mode picker menu. Matched by text content (e.g., "Fast", "Pro"). |
| `sign-in` | Sign-in button/link. If visible, the adapter delegates to the login handler. |

### Login Configuration

```json
{
  "login": {
    "url": "https://accounts.google.com",
    "profile_subdir": "gemini_login",
    "success_indicators": {
      "titles": ["Google Account"],
      "urls": ["/chat", "/app"],
      "selectors": [".logged-in-indicator"]
    },
    "timeout": 300
  }
}
```

| Field | Description |
|-------|-------------|
| `url` | Login page URL (opened in visible window for manual sign-in). |
| `profile_subdir` | Subdirectory under `profile-dir` for this service's persistent login profile. |
| `success_indicators` | How to detect successful login. Uses OR logic — any match = logged in. |
| `success_indicators.titles` | Page title substrings indicating logged-in state. |
| `success_indicators.urls` | URL substrings indicating logged-in state. |
| `success_indicators.selectors` | CSS selectors that are only present when logged in. |
| `timeout` | Seconds to wait for the user to complete login before giving up. |

---

## MCP Protocol & Tools

### JSON-RPC Interface

The server implements the [Model Context Protocol](https://modelcontextprotocol.io/) using JSON-RPC 2.0 over stdin/stdout (client mode) or HTTP (server mode).

**Standard MCP Methods:**

| Method | Description |
|--------|-------------|
| `initialize` | Handshake — returns protocol version, capabilities, and server info. Must be called first. |
| `tools/list` | Returns all available tools with their input schemas. |
| `tools/call` | Executes a specific tool by name with provided arguments. |
| `resources/list` | Lists available resources (currently empty). |
| `resources/templates/list` | Lists resource templates (currently empty). |
| `prompts/list` | Lists prompt templates (currently empty). |

### Available MCP Tools

#### 1. `get_available_tasks`

Discover what tasks and adapters are configured.

**Parameters:** None

**Response:**
```json
{
  "content": [{
    "type": "text",
    "text": "{\"thinking\": {\"adapter\": \"gemini\", \"description\": \"Deep reasoning via Google Gemini\"}}"
  }]
}
```

#### 2. `send_quick_message`

Send a one-shot prompt. Each call opens a fresh chat — no conversation history.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `prompt` | string | yes | The exact text to send to the LLM. |
| `task` | string (enum) | yes | Task name from config (e.g., `"thinking"`). |
| `model` | string (enum) | yes | Model variant (e.g., `"Fast"`, `"Thinking"`, `"Pro"`). |

**Response:**
```json
{
  "content": [{ "type": "text", "text": "The LLM's response text..." }]
}
```

#### 3. `start_chat_session`

Open a persistent multi-turn chat session. The session holds an exclusive browser slot — always call `end_chat_session` when done.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `task` | string (enum) | yes | Task name. |
| `model` | string (enum) | yes | Initial model variant. Can be overridden per-message. |

**Response:**
```json
{
  "session_id": "a1b2c3d4...",
  "task": "thinking",
  "model": "Fast",
  "created_at": "2025-01-15T10:30:00Z"
}
```

#### 4. `send_chat_message`

Send a message within an existing session. Prior conversation context is preserved in the browser page.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | string | yes | Session ID from `start_chat_session`. |
| `prompt` | string | yes | The next message to send. |
| `model` | string (enum) | no | Per-turn model override. If different from current, the adapter switches the model picker. |

**Response:**
```json
{
  "content": [{ "type": "text", "text": "Response to this turn..." }],
  "session_id": "a1b2c3d4..."
}
```

**Error Codes:**
- `404` — Session not found (expired or never existed). Start a new session.
- `410` — Session dead (page closed, login expired, or unrecoverable error). Start a new session.

#### 5. `end_chat_session`

Close a session and free its browser slot. Safe to call on already-ended sessions.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | string | yes | Session ID to close. |

**Response:**
```json
{ "status": "ended", "session_id": "a1b2c3d4..." }
```

### Example JSON-RPC Exchange

```json
// → Request (stdin)
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "send_quick_message",
    "arguments": {
      "prompt": "Explain quantum computing in simple terms",
      "task": "thinking",
      "model": "Thinking"
    }
  },
  "id": 1
}

// ← Response (stdout)
{
  "jsonrpc": "2.0",
  "result": {
    "content": [{
      "type": "text",
      "text": "Quantum computing uses quantum bits (qubits) that can exist in multiple states simultaneously..."
    }]
  },
  "id": 1
}
```

---

## HTTP API Reference

When running in server mode, the following REST endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check. Returns `{"status": "ok", "timestamp": "..."}`. |
| `/api/config` | GET | Current server configuration snapshot (headless mode, pool size, etc.). |
| `/api/tasks` | GET | List all configured tasks with adapter names and descriptions. |
| `/api/stats` | GET | Runtime statistics: browser count, active sessions, request count, connected clients. |
| `/api/register-client` | POST | Register an IDE client. Body: `{"client_id": "uuid"}`. |
| `/api/unregister-client` | POST | Unregister a client. Triggers shutdown countdown if last client. |
| `/api/query` | POST | One-shot query. Body: `{"prompt": "...", "task": "thinking", "model": "Fast"}`. |
| `/api/session/start` | POST | Start multi-turn session. Body: `{"task": "thinking", "model": "Fast"}`. |
| `/api/session/{id}/message` | POST | Send message in session. Body: `{"prompt": "...", "model": "Fast"}`. |
| `/api/session/{id}/end` | POST | End session and free browser slot. |
| `/api/sessions` | GET | List all active sessions with metadata. |
| `/api/shutdown` | POST | Gracefully shut down the server. |

---

## Configuring MCP for AI Tools

The MCP client is started by AI tools as a subprocess. Each tool has its own configuration format to define MCP servers.

### Claude Desktop

Add to your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "web-chat": {
      "command": "python",
      "args": [
        "D:/web-chat/main.py",
        "--no-headless",
        "--max-browsers", "3"
      ]
    }
  }
}
```

### Claude Code (CLI)

Add to your Claude Code MCP settings:

- **Project-level**: `.claude/mcp.json` in your project root
- **User-level**: `~/.claude/mcp.json`

```json
{
  "mcpServers": {
    "web-chat": {
      "command": "python",
      "args": [
        "D:/web-chat/main.py",
        "--max-browsers", "2"
      ]
    }
  }
}
```

Or with a virtual environment:

```json
{
  "mcpServers": {
    "web-chat": {
      "command": "D:/web-chat/.venv/Scripts/python.exe",
      "args": [
        "D:/web-chat/main.py",
        "--no-headless"
      ]
    }
  }
}
```

### VS Code (Copilot / MCP Extension)

Add to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "web-chat": {
        "command": "python",
        "args": [
          "D:/web-chat/main.py",
          "--max-browsers", "2"
        ]
      }
    }
  }
}
```

Or in `.vscode/mcp.json` at your project root:

```json
{
  "servers": {
    "web-chat": {
      "command": "python",
      "args": ["D:/web-chat/main.py"]
    }
  }
}
```

### Cline

Add to Cline's MCP settings (accessible via Cline settings UI → MCP Servers):

```json
{
  "mcpServers": {
    "web-chat": {
      "command": "python",
      "args": [
        "D:/web-chat/main.py",
        "--max-browsers", "2",
        "--no-headless"
      ]
    }
  }
}
```

### Cursor

Add to Cursor's MCP configuration (Settings → MCP):

```json
{
  "mcpServers": {
    "web-chat": {
      "command": "python",
      "args": ["D:/web-chat/main.py"]
    }
  }
}
```

### Any MCP-Compatible Client

The server speaks standard MCP over stdin/stdout. Any client that can:

1. Spawn `python main.py` as a subprocess
2. Write JSON-RPC 2.0 to its stdin
3. Read JSON-RPC 2.0 from its stdout

...can use this server. The lifecycle is:

```
Client                          Server (stdin/stdout)
  │                                │
  │─── initialize ────────────────►│
  │◄── capabilities ──────────────│
  │                                │
  │─── tools/list ────────────────►│
  │◄── tool definitions ──────────│
  │                                │
  │─── tools/call ────────────────►│  (send_quick_message, etc.)
  │◄── result ────────────────────│
  │                                │
  │    (close stdin to exit)       │
```

---

## Adding a New Adapter

To add support for a new LLM service (e.g., ChatGPT, Claude web, Perplexity), follow these three steps:

### Step 1: Create the Adapter File

Create a new directory and file under `mcp_manager/adapters/`:

```
mcp_manager/adapters/
└── chatgpt/
    ├── __init__.py
    └── chatgpt_adapter.py
```

Implement the adapter by extending `BaseAdapter`:

```python
# mcp_manager/adapters/chatgpt/chatgpt_adapter.py

import asyncio
import logging
from mcp_manager.adapters.base_adapter import BaseAdapter
from mcp_manager.login_handler import handle_login

logger = logging.getLogger(__name__)


class ChatGPTAdapter(BaseAdapter):
    """Adapter for OpenAI ChatGPT browser automation."""

    async def process(self, prompt, model, page=None, **kwargs):
        """One-shot: navigate, login, send prompt, extract response."""

        # 1. Navigate to the target URL
        await page.goto(self.url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 2. Check if login is needed
        sign_in_selector = self.get_selector("sign-in")
        if sign_in_selector:
            sign_in = page.locator(sign_in_selector)
            if await sign_in.is_visible():
                login_config = self.config.get("login", {})
                await handle_login(self.task_name, page.context, login_config)
                await page.goto(self.url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

        # 3. Select the model
        await self._select_model(page, model)

        # 4. Enable temp chat if configured
        await self.enable_temp_chat(page)

        # 5. Wait for the input field
        input_selector = self.get_selector("message-box")
        await page.wait_for_selector(input_selector, state="visible", timeout=10000)

        # 6. Capture baseline response count
        complete_selector = self.get_selector("response-complete")
        baseline = await page.locator(complete_selector).count()

        # 7. Type and send the prompt
        input_el = page.locator(input_selector).first
        await input_el.click()
        await page.keyboard.insert_text(prompt)
        await page.keyboard.press("Enter")

        # 8. Wait for new response to complete
        while await page.locator(complete_selector).count() <= baseline:
            await asyncio.sleep(1)

        # 9. Extract the response
        container_selector = self.get_selector("response-container")
        containers = page.locator(container_selector)
        last = containers.last
        return await last.inner_text()

    async def start_session(self, page, model):
        """Initialize a multi-turn session."""
        await page.goto(self.url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Handle login if needed
        # ... (similar to process())

        await self._select_model(page, model)
        await self.enable_temp_chat(page)

        complete_selector = self.get_selector("response-complete")
        baseline = await page.locator(complete_selector).count()

        return {
            "model": model,
            "last_complete_count": baseline,
        }

    async def send_in_session(self, page, prompt, state, model=None):
        """Send one turn in an existing session."""
        # Switch model if requested
        if model and model != state["model"]:
            await self._select_model(page, model)
            state["model"] = model

        # Type and send
        input_selector = self.get_selector("message-box")
        input_el = page.locator(input_selector).first
        await input_el.click()
        await page.keyboard.insert_text(prompt)
        await page.keyboard.press("Enter")

        # Wait for completion
        complete_selector = self.get_selector("response-complete")
        while await page.locator(complete_selector).count() <= state["last_complete_count"]:
            await asyncio.sleep(1)

        # Extract and update state
        state["last_complete_count"] = await page.locator(complete_selector).count()
        container_selector = self.get_selector("response-container")
        return await page.locator(container_selector).last.inner_text()

    async def _select_model(self, page, model):
        """Click the model picker and select the desired model."""
        picker_selector = self.get_selector("mode-picker")
        if not picker_selector:
            return
        picker = page.locator(picker_selector).first
        await picker.click()
        await asyncio.sleep(0.5)

        item_selector = self.get_selector("mode-item")
        items = page.locator(item_selector)
        count = await items.count()
        for i in range(count):
            text = await items.nth(i).inner_text()
            if model.lower() in text.lower():
                await items.nth(i).click()
                await asyncio.sleep(0.5)
                return
        logger.warning(f"Model '{model}' not found in picker")
```

### Step 2: Register the Adapter

Edit `mcp_manager/adapters/adapter_factory.py` — add your import and registration in `_auto_register()`:

```python
def _auto_register():
    """Auto-register built-in adapters."""
    from mcp_manager.adapters.gemini.gemini_adapter import GeminiAdapter
    register_adapter("gemini", GeminiAdapter)

    # Add your new adapter here:
    from mcp_manager.adapters.chatgpt.chatgpt_adapter import ChatGPTAdapter
    register_adapter("chatgpt", ChatGPTAdapter)
```

### Step 3: Add Task Configuration

Add a new task entry in `mcp_manager/config.json`:

```json
{
  "task": {
    "thinking": { ... },

    "chatgpt_reasoning": {
      "adapter": "chatgpt",
      "description": "Advanced reasoning via OpenAI ChatGPT. Best for code generation and analysis.",
      "url": "https://chat.openai.com",
      "models": ["GPT-4o", "GPT-4o-mini", "o1"],
      "login": {
        "url": "https://auth0.openai.com/authorize",
        "profile_subdir": "chatgpt_login",
        "success_indicators": {
          "titles": ["ChatGPT"],
          "urls": ["/chat", "/c/"],
          "selectors": ["[data-testid='chat-input']"]
        },
        "timeout": 300
      },
      "selectors": {
        "temp-chat": ["button[data-testid='temp-chat']"],
        "message-box": [
          "[data-testid='chat-input']",
          "textarea[placeholder*='Message']"
        ],
        "response-container": [".markdown", "[data-message-author-role='assistant']"],
        "response-complete": ["[data-testid='response-complete']", ".result-streaming:not(.streaming)"],
        "mode-picker": ["[data-testid='model-switcher']"],
        "mode-item": ["[data-testid='model-option']"],
        "sign-in": ["[data-testid='login-button']"]
      }
    }
  }
}
```

That's it. Restart the server, and the new task appears in `get_available_tasks` and becomes callable via `send_quick_message`.

### BaseAdapter Interface Reference

Every adapter must extend `BaseAdapter` and implement at minimum the `process()` method. For multi-turn support, also implement `start_session()` and `send_in_session()`.

```python
class BaseAdapter(ABC):

    def __init__(self, task_name: str, task_config: dict):
        """Automatically sets self.task_name, self.config, self.adapter_name,
        self.description, self.url, self.selectors from task_config."""

    @abstractmethod
    async def process(self, prompt: str, model: str, page=None, **kwargs) -> str:
        """One-shot execution. Navigate, login, send, wait, extract, return."""

    async def start_session(self, page, model: str) -> dict:
        """Initialize multi-turn session. Return opaque state dict."""

    async def send_in_session(self, page, prompt: str, state: dict, model: str = None) -> str:
        """Send one turn in existing session. Mutate state. Return response or 'LOGIN_EXPIRED...'."""

    async def enable_temp_chat(self, page):
        """Toggle temp chat if configured. Built-in — usually no override needed."""

    def get_selector(self, key: str, fallback=None) -> str:
        """Get first selector for a key from config."""

    def get_all_selectors(self, key: str) -> list:
        """Get all fallback selectors for a key."""
```

**Key rules for adapter implementations:**

1. **Never create your own Playwright browser or context.** Always use the `page` provided by the pool/session manager.
2. **`process()` is self-contained.** It must handle navigation, login, prompt submission, waiting, and extraction in a single call.
3. **`send_in_session()` must NOT re-navigate.** The page is already on the chat. Just type, send, wait, and extract.
4. **Return `"LOGIN_EXPIRED..."` from `send_in_session()`** if you detect that the session's auth has expired (e.g., page redirected to login). The session manager will mark the session as dead.
5. **Mutate `state` in place** in `send_in_session()` — especially `state["last_complete_count"]` or equivalent baseline counters.

---

## Session Management

Sessions provide multi-turn conversation support over a persistent browser page.

### Session Lifecycle

```
start_chat_session          →  Acquires dedicated browser slot
                               Calls adapter.start_session()
                               Returns session_id

send_chat_message (×N)      →  Serialized via per-session lock
                               Calls adapter.send_in_session()
                               Model switching allowed per-turn

end_chat_session            →  Releases dedicated browser slot
                               Closes browser context
```

### Session Properties

- **Exclusive browser slot**: Each session owns a dedicated Playwright context. No sharing with one-shot queries.
- **15-minute idle timeout**: Sessions not used for 15 minutes are automatically reaped.
- **Per-session locking**: Concurrent `send_chat_message` calls to the same session are serialized.
- **Model switching**: You can pass a different `model` on each `send_chat_message` call. The adapter switches the UI model picker.
- **Dead detection**: If the browser page crashes, navigates away, or login expires, the session is marked dead (HTTP 410).

---

## Browser Pool Internals

### Context Lifecycle

```
Spawn (lazy or eager)
  │
  ├── Copy golden profile → pool_<uuid>/ directory
  ├── Launch Playwright context with profile
  ├── Create initial page
  │
  ▼
Available in Pool
  │
  ├── Acquired for one-shot → adapter.process() → Released back
  ├── Acquired as dedicated → session owns it → Released on end
  │
  ▼
Cleanup (idle timeout or explicit close)
  │
  ├── Close Playwright context
  ├── Delete pool_<uuid>/ directory
```

### Pool Optimizations

- **Spawn outside lock**: When a request needs a new context, the spawn happens after releasing the pool lock, allowing other requests to proceed.
- **Dedicated slot isolation**: Session-owned slots are invisible to the rotation pool, preventing preemption.
- **Fire-and-forget close**: Context closing is non-blocking — the pool doesn't wait for browser I/O.
- **Stale lock detection**: If the server crashes, leftover lock files are detected via PID checks and reclaimed.

---

## Login & Authentication Flow

```
First Request to a Service
  │
  ├── 1. Adapter detects sign-in element visible on page
  ├── 2. Delegates to LoginHandler
  ├── 3. LoginHandler creates VISIBLE browser window (non-headless)
  ├── 4. Checks if golden profile has valid cookies
  │      ├── YES → Transfer cookies to target context → Done
  │      └── NO  → Continue to manual login
  ├── 5. User completes login in visible window
  ├── 6. LoginHandler detects success via success_indicators
  ├── 7. Cookies transferred to target (ephemeral) context
  ├── 8. Golden profile updated with successful session
  └── 9. All future contexts inherit cookies from golden profile
```

**Golden Profile Location**: `~/.web-proxy/playwright-profiles/_golden/`

The golden profile persists across server restarts. Delete it to force a fresh login.

---

## Error Handling & Recovery

| Scenario | Behavior |
|----------|----------|
| **Server not running** | Client auto-starts server via `server_manager.py` with file locking to prevent races. |
| **Browser context crash** | Pool detects dead context, removes it, spawns replacement on next request. |
| **Login expired mid-session** | Adapter returns `LOGIN_EXPIRED` sentinel. Session is marked dead (HTTP 410). Client must start a new session. |
| **All browser slots busy** | One-shot queries wait for a slot. Session creation returns HTTP 429 if all slots are dedicated. |
| **Server already running with different config** | Client logs a mismatch warning but continues with the existing server's settings. |
| **Last client disconnects** | Server starts a 5-minute shutdown timer. Canceled if a new client connects. |
| **Uncaught adapter error** | Logged with full traceback. Screenshots captured on failure for debugging. |

---

## Troubleshooting

### Login window doesn't appear
Make sure you're using `--no-headless` for first-time setup:
```bash
python main.py --server --no-headless
```

### "No adapter registered" error
Ensure your adapter is imported and registered in `_auto_register()` in `adapter_factory.py`.

### Server port already in use
```bash
# Check what's using the port
lsof -i :8765    # macOS/Linux
netstat -ano | findstr 8765    # Windows

# Or use a different port
python main.py --server --port 8766
```

### Stale PID file preventing server start
```bash
rm ~/.web-proxy/server.pid
```

### Session keeps dying
- Check that your login cookies are still valid (delete golden profile to re-login)
- Increase `--browser-idle-timeout` if sessions are being reaped too early
- Check server logs at `~/.web-proxy/server.log` for detailed error messages

### MCP client not connecting
- Verify the `command` path in your MCP config points to the correct Python interpreter
- Verify `main.py` path is absolute
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Check stderr output — all logs go to stderr, not stdout (stdout is reserved for JSON-RPC)

### Selectors stopped working
Web applications update their UI frequently. If automation breaks:
1. Open the target site in a browser
2. Use DevTools (F12) to inspect the current element structure
3. Update the selectors in `config.json`
4. Restart the server
