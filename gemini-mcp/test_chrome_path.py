"""
Test script to verify Chrome path detection and driver initialization
"""
import sys
from pathlib import Path

print("=" * 60)
print("Testing Chrome Path Detection")
print("=" * 60)

# Test 1: Import config
print("\n1. Testing config import...")
try:
    from config import CHROME_BINARY_PATH, CHROME_PROFILE_DIR
    print("[OK] Config imported successfully")
    print(f"  Chrome path: {CHROME_BINARY_PATH}")
    print(f"  Profile dir: {CHROME_PROFILE_DIR}")
    
    if CHROME_BINARY_PATH:
        if Path(CHROME_BINARY_PATH).exists():
            print(f"[OK] Chrome binary exists at: {CHROME_BINARY_PATH}")
        else:
            print(f"[FAIL] Chrome binary NOT found at: {CHROME_BINARY_PATH}")
            sys.exit(1)
    else:
        print("[FAIL] Chrome path is None")
        sys.exit(1)
except Exception as e:
    print(f"[FAIL] Config import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Test driver initialization (without actually launching)
print("\n2. Testing driver configuration...")
try:
    import undetected_chromedriver as uc
    
    options = uc.ChromeOptions()
    options.binary_location = CHROME_BINARY_PATH
    options.add_argument('--window-size=1920,1080')
    
    print("[OK] ChromeOptions configured")
    print(f"  binary_location: {options.binary_location}")
    print(f"  Type: {type(options.binary_location)}")
    
    if isinstance(options.binary_location, str):
        print("[OK] binary_location is a string")
    else:
        print(f"[FAIL] binary_location is NOT a string: {type(options.binary_location)}")
        sys.exit(1)
        
except Exception as e:
    print(f"[FAIL] Driver configuration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Quick driver launch test (will open browser briefly)
print("\n3. Testing actual driver launch...")
print("   (This will open Chrome briefly, then close it)")
response = input("   Continue? (y/n): ")

if response.lower() == 'y':
    try:
        driver = uc.Chrome(
            options=options,
            user_data_dir=str(CHROME_PROFILE_DIR),
            version_main=None,
            driver_executable_path=None,
            browser_executable_path=CHROME_BINARY_PATH
        )
        print("[OK] Driver launched successfully!")
        driver.quit()
        print("[OK] Driver closed successfully!")
    except Exception as e:
        print(f"[FAIL] Driver launch failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print("   Skipped driver launch test")

print("\n" + "=" * 60)
print("All tests passed!")
print("=" * 60)
