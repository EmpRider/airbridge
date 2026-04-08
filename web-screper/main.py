import logging
import subprocess
import sys
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options

prompt = "gemini test"

# ---------------- LOGGING SETUP ----------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logging.info("Starting script...")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# ---------------- START EDGE ----------------
logging.info("Launching Edge with remote debugging...")
try:
    subprocess.Popen([
        EDGE_PATH,
        "--remote-debugging-port=9222",
        "--user-data-dir=D:\\edge-debug-profile"
    ])
except Exception as e:
    logging.error(f"Failed to start Edge: {e}")
    sys.exit(1)

logging.info("Waiting for Edge to initialize...")
time.sleep(5)

# ---------------- CONNECT SELENIUM ----------------
logging.info("Connecting to Edge via remote debugger...")

edge_options = Options()
edge_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

try:
    driver = webdriver.Edge(options=edge_options)
    logging.info("Connected to Edge successfully.")
except Exception as e:
    logging.error(f"Failed to connect to Edge: {e}")
    sys.exit(1)

# ---------------- TAB HANDLING ----------------
try:
    handles = driver.window_handles
    logging.debug(f"Window handles found: {handles}")

    if not handles:
        logging.error("No window handles found!")
        sys.exit(1)

    driver.switch_to.window(handles[0])
    logging.info("Switched to first tab")

except Exception as e:
    logging.error(f"Tab switching failed: {e}")
    sys.exit(1)

# ---------------- NAVIGATION ----------------
try:
    logging.info("Navigating to Gemini...")
    driver.get("https://gemini.google.com/app")
    time.sleep(8)  # wait for full app load
    logging.debug(f"Current URL: {driver.current_url}")
except Exception as e:
    logging.error(f"Navigation failed: {e}")

# ---------------- SIMULATE JS ----------------
try:
    logging.info("Injecting JS to type and send message...")

    response = driver.execute_async_script("""
        const callback = arguments[0];
    
        const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    
        const actionsBefore = document.querySelectorAll('message-actions').length;
    
        let response = "";
    
        let myInterval = setInterval(() => {
            console.log("Running...");
    
            if (actionsBefore < document.querySelectorAll('message-actions').length) {
                const input = document.querySelectorAll('message-content');
                response = input[input.length - 1].innerText;
    
                clearInterval(myInterval);
    
                // RETURN TO PYTHON
                callback(response);
            }
        }, 2000);
    
        async function run() {
            const input = document.querySelector('[data-placeholder="Ask Gemini"]');
    
            if (!input) {
                callback("ERROR: Input not found");
                return;
            }
    
            input.focus();
    
            document.execCommand('insertText', false, '""" + prompt + """');
    
            await sleep(1000);
    
            input.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                bubbles: true
            }));
        }
    
        run();
    """)

    print("Gemini response:", response)

    logging.info("JS executed successfully.")

except Exception as e:
    logging.error(f"JS execution failed: {e}")

# ---------------- WAIT ----------------
logging.info("Waiting before exit...")
input("Press Enter to exit...")

driver.quit()
logging.info("Browser closed. Script finished.")
