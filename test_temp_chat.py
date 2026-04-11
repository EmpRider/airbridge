"""
Test script for temp chat feature.
Verifies that the --use-temp-chat and --no-temp-chat flags work correctly.
"""
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from mcp_manager.browser import set_temp_chat_preference, get_temp_chat_preference

def test_temp_chat_preference():
    """Test temp chat preference setting and getting."""
    print("Testing temp chat preference...")

    # Test default value
    default_value = get_temp_chat_preference()
    print(f"Default temp chat preference: {default_value}")
    assert default_value == True, "Default should be True"

    # Test setting to False
    set_temp_chat_preference(False)
    value = get_temp_chat_preference()
    print(f"After setting to False: {value}")
    assert value == False, "Should be False after setting"

    # Test setting to True
    set_temp_chat_preference(True)
    value = get_temp_chat_preference()
    print(f"After setting to True: {value}")
    assert value == True, "Should be True after setting"

    print("[PASS] Temp chat preference works correctly\n")

if __name__ == "__main__":
    try:
        test_temp_chat_preference()
        print("=" * 50)
        print("All temp chat tests passed!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
