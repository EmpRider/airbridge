"""
Test script for HTTP server startup and basic functionality.
"""
import time
import httpx
import subprocess
import sys

def test_server_startup():
    """Test that server starts and responds to health check."""
    print("=" * 60)
    print("Testing HTTP Server Startup")
    print("=" * 60)

    # Start server in background
    print("\n1. Starting server...")
    process = subprocess.Popen(
        [sys.executable, "main.py", "--server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to start
    print("   Waiting for server to be ready...")
    max_attempts = 30
    for i in range(max_attempts):
        try:
            response = httpx.get("http://localhost:8765/api/health", timeout=2.0)
            if response.status_code == 200:
                print(f"   ✓ Server ready after {i+1} attempts")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("   ✗ Server failed to start within 30 seconds")
        process.terminate()
        return False

    # Test health endpoint
    print("\n2. Testing health endpoint...")
    try:
        response = httpx.get("http://localhost:8765/api/health", timeout=5.0)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        assert response.status_code == 200
        print("   ✓ Health check passed")
    except Exception as e:
        print(f"   ✗ Health check failed: {e}")
        process.terminate()
        return False

    # Test stats endpoint
    print("\n3. Testing stats endpoint...")
    try:
        response = httpx.get("http://localhost:8765/api/stats", timeout=5.0)
        print(f"   Status: {response.status_code}")
        stats = response.json()
        print(f"   Stats: {stats}")
        assert response.status_code == 200
        assert stats["browsers"] == 0  # No browsers spawned yet (lazy)
        assert stats["active_tabs"] == 0
        assert stats["connected_clients"] == 0
        print("   ✓ Stats check passed")
    except Exception as e:
        print(f"   ✗ Stats check failed: {e}")
        process.terminate()
        return False

    # Test tasks endpoint
    print("\n4. Testing tasks endpoint...")
    try:
        response = httpx.get("http://localhost:8765/api/tasks", timeout=5.0)
        print(f"   Status: {response.status_code}")
        tasks = response.json()
        print(f"   Available tasks: {list(tasks.keys())}")
        assert response.status_code == 200
        assert "thinking" in tasks
        print("   ✓ Tasks check passed")
    except Exception as e:
        print(f"   ✗ Tasks check failed: {e}")
        process.terminate()
        return False

    # Shutdown server
    print("\n5. Shutting down server...")
    try:
        response = httpx.post("http://localhost:8765/api/shutdown", timeout=5.0)
        print(f"   Status: {response.status_code}")
        print("   ✓ Shutdown initiated")
    except Exception as e:
        print(f"   ✗ Shutdown failed: {e}")
        process.terminate()
        return False

    # Wait for process to exit
    try:
        process.wait(timeout=10)
        print("   ✓ Server stopped cleanly")
    except subprocess.TimeoutExpired:
        print("   ✗ Server did not stop, killing...")
        process.kill()
        return False

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_server_startup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
