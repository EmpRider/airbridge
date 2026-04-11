"""
Server Manager - Handles server lifecycle with multi-client safety.

Provides file locking to prevent race conditions when multiple IDEs start simultaneously.
"""
import os
import sys
import time
import socket
import subprocess
import logging
import psutil
import httpx
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Default server settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PID_FILE = Path.home() / ".web-proxy" / "server.pid"
DEFAULT_LOCK_FILE = Path.home() / ".web-proxy" / "server.lock"


@contextmanager
def file_lock(lock_file: Path, timeout: int = 30):
    """Cross-platform file locking context manager.

    Args:
        lock_file: Path to lock file
        timeout: Maximum time to wait for lock (seconds)

    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Create lock file
    lock_fd = None
    start_time = time.time()

    try:
        # Try to acquire lock
        while True:
            try:
                # Open file in exclusive mode
                lock_fd = os.open(
                    str(lock_file),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                break
            except FileExistsError:
                # Lock file exists, wait and retry
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock on {lock_file} within {timeout}s")

                time.sleep(0.1)

        # Write PID to lock file
        os.write(lock_fd, str(os.getpid()).encode())

        logger.debug(f"Acquired lock on {lock_file}")
        yield

    finally:
        # Release lock
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                lock_file.unlink(missing_ok=True)
                logger.debug(f"Released lock on {lock_file}")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is in use.

    Args:
        port: Port number to check
        host: Host address

    Returns:
        True if port is in use, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception as e:
        logger.error(f"Error checking port {port}: {e}")
        return False


def is_server_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE
) -> bool:
    """Check if server is actually running (not just PID file exists).

    Performs multiple checks:
    1. PID file exists
    2. Process with that PID exists
    3. Port is listening
    4. Health endpoint responds

    Args:
        host: Server host
        port: Server port
        pid_file: Path to PID file

    Returns:
        True if server is running, False otherwise
    """
    # Check PID file
    if not pid_file.exists():
        logger.debug("PID file does not exist")
        return False

    try:
        # Check process exists
        pid = int(pid_file.read_text().strip())
        if not psutil.pid_exists(pid):
            logger.debug(f"Process {pid} does not exist")
            # Clean up stale PID file
            pid_file.unlink(missing_ok=True)
            return False

        # Check port listening
        if not is_port_in_use(port, host):
            logger.debug(f"Port {port} is not in use")
            return False

        # Check health endpoint
        try:
            response = httpx.get(f"http://{host}:{port}/api/health", timeout=2.0)
            if response.status_code == 200:
                logger.debug("Server health check passed")
                return True
            else:
                logger.debug(f"Server health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.debug(f"Server health check failed: {e}")
            return False

    except Exception as e:
        logger.error(f"Error checking server status: {e}")
        return False


def start_server_safe(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE,
    lock_file: Path = DEFAULT_LOCK_FILE,
    **kwargs
):
    """Start server with file lock to prevent multiple instances.

    Scenario: 3 IDEs start at same time
    - IDE 1: Acquires lock, starts server
    - IDE 2: Waits for lock, sees server running, connects
    - IDE 3: Waits for lock, sees server running, connects

    Args:
        host: Server host
        port: Server port
        pid_file: Path to PID file
        lock_file: Path to lock file
        **kwargs: Additional arguments to pass to server
    """
    logger.info("Attempting to start server...")

    try:
        with file_lock(lock_file, timeout=30):
            # Check if server already running
            if is_server_running(host, port, pid_file):
                logger.info("Server already running")
                return

            # Start server in background
            logger.info(f"Starting server on {host}:{port}...")

            # Build command
            cmd = [sys.executable, "main.py", "--server"]

            # Add optional arguments
            if host != DEFAULT_HOST:
                cmd.extend(["--host", host])
            if port != DEFAULT_PORT:
                cmd.extend(["--port", str(port)])

            # Add other kwargs as CLI args
            for key, value in kwargs.items():
                if value is True:
                    cmd.append(f"--{key.replace('_', '-')}")
                elif value is not False and value is not None:
                    cmd.extend([f"--{key.replace('_', '-')}", str(value)])

            # Start process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Detach from parent
            )

            logger.info(f"Server process started with PID {process.pid}")

            # Wait for server to be ready
            wait_for_server(host, port, timeout=30)

            logger.info("Server started successfully")

    except TimeoutError as e:
        logger.error(f"Failed to acquire lock: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise


def wait_for_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: int = 30
):
    """Wait for server to be ready.

    Args:
        host: Server host
        port: Server port
        timeout: Maximum time to wait (seconds)

    Raises:
        TimeoutError: If server doesn't become ready within timeout
    """
    logger.info(f"Waiting for server to be ready (timeout: {timeout}s)...")

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"http://{host}:{port}/api/health", timeout=2.0)
            if response.status_code == 200:
                logger.info("Server is ready")
                return
        except Exception:
            pass

        time.sleep(0.5)

    raise TimeoutError(f"Server did not become ready within {timeout}s")


def stop_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE
):
    """Stop the server gracefully.

    Args:
        host: Server host
        port: Server port
        pid_file: Path to PID file
    """
    logger.info("Stopping server...")

    try:
        # Try graceful shutdown via API
        try:
            response = httpx.post(
                f"http://{host}:{port}/api/shutdown",
                timeout=5.0
            )
            if response.status_code == 200:
                logger.info("Server shutdown initiated via API")

                # Wait for server to stop
                for _ in range(10):
                    if not is_server_running(host, port, pid_file):
                        logger.info("Server stopped successfully")
                        return
                    time.sleep(1)
        except Exception as e:
            logger.debug(f"Could not shutdown via API: {e}")

        # Fallback: Kill process
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    process.terminate()
                    process.wait(timeout=10)
                    logger.info(f"Server process {pid} terminated")

                pid_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Error killing server process: {e}")

    except Exception as e:
        logger.error(f"Error stopping server: {e}", exc_info=True)


def get_server_stats(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT
) -> dict:
    """Get server statistics.

    Args:
        host: Server host
        port: Server port

    Returns:
        Dictionary with server stats
    """
    try:
        response = httpx.get(f"http://{host}:{port}/api/stats", timeout=5.0)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}
