"""
MCP Adapter Server - Entry Point
Routes execution to the modular mcp_manager package.
"""
import sys
import os

# Ensure the project root is on sys.path for clean imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from mcp_manager.server import main

if __name__ == "__main__":
    main()
