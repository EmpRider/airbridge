"""
Simple test script to verify Gemini adapter with proper login handling and cleanup.
"""
import asyncio
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from mcp_manager.browser_pool import BrowserPool
from mcp_manager.adapters.adapter_factory import create_adapter

async def test_gemini():
    """Test Gemini adapter with browser pool."""
    print("=" * 60)
    print("Testing Gemini Adapter")
    print("=" * 60)
    
    pool = None
    
    try:
        # Create browser pool (headless=False to see login if needed)
        print("\n1. Initializing browser pool (non-headless mode)...")
        pool = BrowserPool(
            max_contexts=2,
            lazy_spawn=True,
            default_headless=False
        )
        await pool.start()
        print("   [OK] Browser pool started")
        
        # Create adapter
        print("\n2. Creating Gemini adapter...")
        adapter = create_adapter("thinking")
        print("   [OK] Adapter created")
        
        # Test query
        print("\n3. Sending test query...")
        test_prompt = "What is 2+2? Answer in one sentence."
        print(f"   Prompt: {test_prompt}")
        
        result = await pool.execute_task(
            adapter=adapter,
            prompt=test_prompt,
            model="Thinking",
            headless=False
        )
        
        print(f"\n4. Response received:")
        if result.startswith("ERROR"):
            print(f"   [FAIL] {result}")
            return False
        else:
            print(f"   [OK] {result[:200]}..." if len(result) > 200 else f"   [OK] {result}")
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        print("\n5. Cleaning up...")
        if pool:
            try:
                await pool.stop()
                print("   [OK] Browser pool stopped")
            except Exception as e:
                print(f"   [FAIL] Cleanup error: {e}")

if __name__ == "__main__":
    try:
        success = asyncio.run(test_gemini())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
