# Temporary Chat Feature

## Overview

The MCP server now supports controlling whether to use Gemini's temporary chat mode via CLI arguments. This gives you control over whether your conversations are saved to your Google account history.

**Important:** The temp chat setting is configured via CLI arguments only, not as an MCP tool parameter. This ensures consistent behavior across all requests in a session.

## Default Behavior

**Temporary chat is ENABLED by default** for privacy reasons.

## Usage

### CLI Arguments

```bash
# Use temporary chat (default)
python main.py --use-temp-chat

# Use normal chat with history
python main.py --no-temp-chat
```

### MCP Configuration

```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--no-temp-chat"
    ]
  }
}
```

## When to Use Each Mode

### Use Temporary Chat (default) when:
- You want privacy - conversations won't be saved
- You're testing or debugging
- You don't need to review the conversation later
- You're handling sensitive information

### Use Normal Chat when:
- You want to review conversation history later
- You're building a persistent chat session
- You need to access conversations from Gemini's web interface
- You want to continue conversations across sessions

## How It Works

1. **CLI Level**: The `--use-temp-chat` or `--no-temp-chat` flag sets the global preference when the server starts
2. **Browser Level**: The adapter checks the preference and clicks the "Temporary chat" button if enabled

The setting applies to all requests in that server session.

## Implementation Details

### Files Modified

1. **mcp_manager/server.py**
   - Added `--use-temp-chat` and `--no-temp-chat` CLI arguments
   - Sets global preference on server startup

2. **mcp_manager/browser.py**
   - Added `set_temp_chat_preference()` function
   - Added `get_temp_chat_preference()` function
   - Global `_use_temp_chat` variable (default: True)

3. **mcp_manager/adapters/gemini/gemini_adapter.py**
   - Checks temp chat preference before clicking temp chat button
   - Logs whether temp chat is enabled or disabled

## Testing

Run the test script to verify the feature works:

```bash
python test_temp_chat.py
```

Expected output:
```
Testing temp chat preference...
Default temp chat preference: True
After setting to False: False
After setting to True: True
[PASS] Temp chat preference works correctly

==================================================
All temp chat tests passed!
==================================================
```

## Logging

The server logs temp chat activity:

```
INFO: Temp chat preference set to: True
INFO: Temp chat preference: True
INFO: Activating Temporary Chat via: button[aria-label="Temporary chat"]
```

Or when disabled:

```
INFO: Temp chat preference set to: False
INFO: Temp chat preference: False
INFO: Temp chat disabled, using normal chat mode
```

## Examples

### Example 1: Privacy-focused setup (default)

```json
{
  "query_premium_model": {
    "command": "python",
    "args": ["D:\\web-chat\\main.py"]
  }
}
```

All conversations use temporary chat by default.

### Example 2: Persistent chat for development

```json
{
  "query_premium_model": {
    "command": "python",
    "args": [
      "D:\\web-chat\\main.py",
      "--no-temp-chat"
    ]
  }
}
```

All conversations are saved to your Google account.

## Troubleshooting

### Temp chat button not found

If you see this warning:
```
WARNING: Temp-chat selector button[aria-label="Temporary chat"] failed
```

This means:
- The button selector in config.json may be outdated
- You're already in temp chat mode
- The Gemini UI has changed

**Solution**: Update the selector in `mcp_manager/config.json`:

```json
{
  "task": {
    "thinking": {
      "selectors": {
        "temp-chat": [
          "button[aria-label=\"Temporary chat\"]",
          "button[aria-label=\"Start temporary chat\"]"
        ]
      }
    }
  }
}
```

### Temp chat not activating

Check the log file for:
```
INFO: Temp chat preference: True
INFO: Activating Temporary Chat via: ...
```

If you see "Temp chat disabled", the preference is set to False. Check your CLI args or tool parameters.

## Future Enhancements

Potential improvements:
- Auto-detect if already in temp chat mode
- Support for other chat providers (Claude, ChatGPT, etc.)
- Per-task temp chat preferences in config.json
- Session-based temp chat control
