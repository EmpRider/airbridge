"""
MCP Adapter Server — Entry Point

Supports both server mode (HTTP server) and client mode (MCP JSON-RPC stdio).
"""
import sys
import os
import asyncio
import argparse
import logging

# Ensure the project root is on sys.path for clean imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)


def setup_logging(log_file=None):
    """Set up logging with file + stderr handlers.

    CRITICAL: stdout is reserved for MCP JSON-RPC in client mode. Every log
    handler must target stderr.
    """
    from pathlib import Path

    if log_file is None:
        log_file = Path.home() / ".web-proxy" / "server.log"

    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: Could not create log file at {log_file}: {e}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="MCP Browser Pool Server/Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
MODES:
  Server mode: python main.py --server
  Client mode: python main.py (default)

EXAMPLES:
  # Start HTTP server
  python main.py --server

  # Start HTTP server with custom settings
  python main.py --server --port 8766 --max-browsers 3

  # Start MCP client (auto-starts server if needed)
  python main.py

  # Client with windowed Chrome (forwarded to the auto-started server)
  python main.py --no-headless
        """,
    )

    parser.add_argument("--server", action="store_true", help="Run in server mode (HTTP server)")

    # Server settings
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    parser.add_argument("--pid-file", help="Path to PID file")
    parser.add_argument("--log-file", help="Path to log file")

    # Browser pool settings
    parser.add_argument("--max-browsers", type=int, default=2, help="Max browsers in pool (default: 2)")
    parser.add_argument("--max-tabs-per-browser", type=int, default=5, help="Max tabs per browser (default: 5)")
    parser.add_argument("--tab-idle-timeout", type=int, default=300, help="Tab idle timeout seconds (default: 300)")
    parser.add_argument("--browser-idle-timeout", type=int, default=1800, help="Browser idle timeout seconds (default: 1800)")
    parser.add_argument("--no-lazy-spawn", action="store_true", help="Spawn all browsers immediately")
    parser.add_argument("--enable-images", action="store_true", help="Enable image loading (default: disabled)")
    parser.add_argument("--enable-fonts", action="store_true", help="Enable font loading (default: disabled)")

    # Browser settings
    parser.add_argument("--chrome-path", help="Path to Chrome executable")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in windowed mode (default: headless)")
    parser.add_argument("--no-temp-chat", action="store_true", help="Use normal chat (default: temp chat)")
    parser.add_argument("--profile-dir", help="Custom Chrome profile directory")
    parser.add_argument("--config", help="Path to adapter config JSON file")

    return parser.parse_args()


def _build_server_kwargs(args) -> dict:
    """Build kwargs dict for start_server_safe → gets converted back to CLI flags.

    We always forward every setting that differs from its parser default so
    nothing silently drops. The parser already holds the defaults, so use them.
    """
    kwargs = {}
    # Pool settings — forward if different from parser default
    if args.max_browsers != 2:
        kwargs["max_browsers"] = args.max_browsers
    if args.max_tabs_per_browser != 5:
        kwargs["max_tabs_per_browser"] = args.max_tabs_per_browser
    if args.tab_idle_timeout != 300:
        kwargs["tab_idle_timeout"] = args.tab_idle_timeout
    if args.browser_idle_timeout != 1800:
        kwargs["browser_idle_timeout"] = args.browser_idle_timeout
    if args.no_lazy_spawn:
        kwargs["no_lazy_spawn"] = True
    if args.enable_images:
        kwargs["enable_images"] = True
    if args.enable_fonts:
        kwargs["enable_fonts"] = True
    # Browser
    if args.chrome_path:
        kwargs["chrome_path"] = args.chrome_path
    if args.no_headless:
        kwargs["no_headless"] = True
    if args.no_temp_chat:
        kwargs["no_temp_chat"] = True
    if args.profile_dir:
        kwargs["profile_dir"] = args.profile_dir
    if args.config:
        kwargs["config"] = args.config
    # Misc
    if args.pid_file:
        kwargs["pid_file"] = args.pid_file
    if args.log_file:
        kwargs["log_file"] = args.log_file
    return kwargs


def _build_expected_config(args) -> dict:
    """Fields the client expects to see in /api/config (for mismatch warning)."""
    return {
        "default_headless": not args.no_headless,
        "use_temp_chat": not args.no_temp_chat,
        "max_browsers": args.max_browsers,
    }


def main():
    args = parse_args()
    setup_logging(args.log_file)
    logger = logging.getLogger(__name__)

    try:
        if args.server:
            # ------------------------------------------------------------
            # SERVER MODE
            # ------------------------------------------------------------
            logger.info("Starting in SERVER mode")

            from pathlib import Path
            from mcp_manager.http_server import create_server
            from mcp_manager.browser import get_browser_config, set_temp_chat_preference

            if args.config:
                from mcp_manager.adapters.adapter_factory import load_config
                load_config(args.config)

            headless = not args.no_headless
            use_temp_chat = not args.no_temp_chat
            lazy_spawn = not args.no_lazy_spawn

            profile_dir = Path(args.profile_dir) if args.profile_dir else None

            # Seed the default browser config (lazy Chrome validation now)
            get_browser_config(args.chrome_path, headless, profile_dir)
            set_temp_chat_preference(use_temp_chat)

            pid_file = Path(args.pid_file) if args.pid_file else None

            server = create_server(
                host=args.host,
                port=args.port,
                max_browsers=args.max_browsers,
                max_tabs_per_browser=args.max_tabs_per_browser,
                tab_idle_timeout=args.tab_idle_timeout,
                browser_idle_timeout=args.browser_idle_timeout,
                lazy_spawn=lazy_spawn,
                pid_file=pid_file,
                default_headless=headless,
                use_temp_chat=use_temp_chat,
                chrome_path=args.chrome_path,
                profile_dir=str(profile_dir) if profile_dir else None,
            )

            server.run()

        else:
            # ------------------------------------------------------------
            # CLIENT MODE (MCP JSON-RPC stdio)
            # ------------------------------------------------------------
            logger.info("Starting in CLIENT mode")

            from mcp_manager.mcp_client import MCPClient, mcp_client_loop
            from mcp_manager.server_manager import start_server_safe, is_server_running

            server_kwargs = _build_server_kwargs(args)
            expected_config = _build_expected_config(args)

            # Create MCP client — pass kwargs so the fallback restart can forward them too
            client = MCPClient(
                host=args.host,
                port=args.port,
                server_kwargs=server_kwargs,
                expected_config=expected_config,
            )

            asyncio.run(mcp_client_loop(client))

    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
