"""
Test script to verify MCP server fixes.
Tests the browser config singleton update and adapter signature.
"""
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from mcp_manager.browser import get_browser_config
from mcp_manager.adapters.adapter_factory import create_adapter

def test_browser_config_updates():
    """Test that browser config singleton updates correctly."""
    print("Testing browser config singleton updates...")

    # Initial config with headless=True
    config1 = get_browser_config(headless=True)
    print(f"Initial config: headless={config1.headless}")
    assert config1.headless == True, "Initial headless should be True"

    # Update to headless=False
    config2 = get_browser_config(headless=False)
    print(f"Updated config: headless={config2.headless}")
    assert config2.headless == False, "Updated headless should be False"
    assert config1 is config2, "Should be same singleton instance"

    print("[PASS] Browser config singleton updates correctly\n")

def test_adapter_signature():
    """Test that adapter has correct process() signature."""
    print("Testing adapter signature...")

    adapter = create_adapter("thinking")
    print(f"Created adapter: {adapter}")

    # Check that process method accepts model parameter
    import inspect
    sig = inspect.signature(adapter.process)
    params = list(sig.parameters.keys())
    print(f"Process method parameters: {params}")

    assert "model" in params, "process() should have 'model' parameter"
    assert "prompt" in params, "process() should have 'prompt' parameter"
    assert "chrome_path" in params, "process() should have 'chrome_path' parameter"
    assert "headless" in params, "process() should have 'headless' parameter"

    print("[PASS] Adapter signature is correct\n")

if __name__ == "__main__":
    try:
        test_browser_config_updates()
        test_adapter_signature()
        print("=" * 50)
        print("All tests passed!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
