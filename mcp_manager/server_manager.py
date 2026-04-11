"""
Server Manager — lifecycle + multi-client safety.

Key guarantees:
- Subprocess stdout/stderr are captured to a startup log so failures are visible.
- Stale lock files (lock PID dead) are reclaimed instead of waiting 30s.
- PID file verification checks the process actually looks like *our* server.
- When startup fails, the tail of the server log is surfaced in the exception.
"""
import os
import sys
import time
import json
import socket
import subprocess
import logging
import psutil
import httpx
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Default server settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PID_FILE = Path.home() / ".web-proxy" / "server.pid"
DEFAULT_LOCK_FILE = Path.home() / ".web-proxy" / "server.lock"
DEFAULT_STARTUP_LOG = Path.home() / ".web-proxy" / "server-startup.log"
DEFAULT_SERVER_LOG = Path.home() / ".web-proxy" / "server.log"

# Server identity marker — used to tell a real server PID from a reused PID
SERVER_MARKER = "main.py"


# ----------------------------------------------------------------------
# Lock file (with stale-lock detection)
# ----------------------------------------------------------------------
def _read_lock_pid(lock_file: Path) -> Optional[int]:
    try:
        content = lock_file.read_text().strip()
        return int(content) if content else None
    except Exception:
        return None


def _is_stale_lock(lock_file: Path) -> bool:
    """A lock is stale if its owning PID is dead or not our server."""
    pid = _read_lock_pid(lock_file)
    if pid is None:
        return True  # unreadable → treat as stale
    if not psutil.pid_exists(pid) or not _pid_is_our_server(pid):
        return True
    return False


@contextmanager
def file_lock(lock_file: Path, timeout: int = 30):
    """Cross-platform file lock with stale-lock detection."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    start_time = time.time()

    try:
        while True:
            try:
                lock_fd = os.open(
                    str(lock_file),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                )
                break
            except FileExistsError:
                # Check for stale lock — if the owner is dead, reclaim it.
                if _is_stale_lock(lock_file):
                    logger.warning(
                        f"Reclaiming stale lock {lock_file} "
                        f"(previous owner PID {_read_lock_pid(lock_file)} is dead)"
                    )
                    try:
                        lock_file.unlink()
                    except Exception as e:
                        logger.error(f"Could not remove stale lock: {e}")
                    continue

                if time.time() - start_time > timeout:
                    raise TimeoutError(
                        f"Could not acquire lock on {lock_file} within {timeout}s "
                        f"(held by PID {_read_lock_pid(lock_file)})"
                    )
                time.sleep(0.1)

        os.write(lock_fd, str(os.getpid()).encode())
        logger.debug(f"Acquired lock on {lock_file}")
        yield

    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                lock_file.unlink(missing_ok=True)
                logger.debug(f"Released lock on {lock_file}")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")


# ----------------------------------------------------------------------
# Port / server checks
# ----------------------------------------------------------------------
def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0
    except Exception as e:
        logger.error(f"Error checking port {port}: {e}")
        return False


def _pid_is_our_server(pid: int) -> bool:
    """Heuristic: does this PID look like our main.py server?

    Guards against OS PID reuse — we don't want notepad.exe to be interpreted
    as a running server just because its PID happens to match our pid file.
    """
    try:
        proc = psutil.Process(pid)
        name = (proc.name() or "").lower()
        if "python" not in name and "pythonw" not in name:
            # Not a python process — definitely not our server
            return False
        try:
            cmdline = " ".join(proc.cmdline()).lower()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            # Can't inspect; assume OK (Windows sometimes blocks cmdline)
            return True
        return SERVER_MARKER in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def is_server_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE,
) -> bool:
    """Return True only if a real, responsive server is running."""
    if not pid_file.exists():
        logger.debug("PID file does not exist")
        return False

    try:
        pid = int(pid_file.read_text().strip())
    except Exception as e:
        logger.debug(f"PID file unreadable: {e}; removing")
        pid_file.unlink(missing_ok=True)
        return False

    if not psutil.pid_exists(pid):
        logger.debug(f"Process {pid} does not exist; removing stale PID file")
        pid_file.unlink(missing_ok=True)
        return False

    if not _pid_is_our_server(pid):
        logger.warning(
            f"PID {pid} exists but doesn't look like our server — treating PID file as stale"
        )
        pid_file.unlink(missing_ok=True)
        return False

    if not is_port_in_use(port, host):
        logger.debug(f"Port {port} not in use — server is starting or dead")
        return False

    try:
        response = httpx.get(f"http://{host}:{port}/api/health", timeout=2.0)
        if response.status_code == 200:
            return True
        logger.debug(f"Health check returned {response.status_code}")
        return False
    except Exception as e:
        logger.debug(f"Health check failed: {e}")
        return False


# ----------------------------------------------------------------------
# Start server
# ----------------------------------------------------------------------
def _build_server_cmd(host: str, port: int, kwargs: dict) -> list:
    """Convert kwargs → CLI args. Booleans become flags; values are stringified."""
    # Locate main.py relative to this file's parent
    project_root = Path(__file__).resolve().parent.parent
    main_py = project_root / "main.py"

    cmd = [sys.executable, str(main_py), "--server"]
    if host != DEFAULT_HOST:
        cmd.extend(["--host", host])
    if port != DEFAULT_PORT:
        cmd.extend(["--port", str(port)])

    for key, value in kwargs.items():
        if value is None or value is False:
            continue
        flag = f"--{key.replace('_', '-')}"
        if value is True:
            cmd.append(flag)
        else:
            cmd.extend([flag, str(value)])
    return cmd


def _tail_file(path: Path, max_lines: int = 30) -> str:
    try:
        if not path.exists():
            return f"(no log at {path})"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-max_lines:]
        return "\n".join(tail)
    except Exception as e:
        return f"(could not read log: {e})"


def start_server_safe(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE,
    lock_file: Path = DEFAULT_LOCK_FILE,
    startup_log: Path = DEFAULT_STARTUP_LOG,
    startup_timeout: int = 45,
    **kwargs,
):
    """Start the server with file-lock coordination.

    The subprocess's stdout/stderr are redirected to startup_log (NOT devnull)
    so any failures are diagnosable. If startup times out, the last lines of
    the startup log are surfaced in the raised exception.
    """
    logger.info("Attempting to start server...")

    try:
        with file_lock(lock_file, timeout=30):
            if is_server_running(host, port, pid_file):
                logger.info("Server already running")
                return

            # Prepare startup log
            try:
                startup_log.parent.mkdir(parents=True, exist_ok=True)
                # Truncate previous startup log so we only capture this run
                log_handle = open(startup_log, "w", encoding="utf-8")
            except Exception as e:
                logger.warning(
                    f"Could not open startup log {startup_log}: {e}; falling back to DEVNULL"
                )
                log_handle = subprocess.DEVNULL

            cmd = _build_server_cmd(host, port, kwargs)
            logger.info(f"Starting server: {' '.join(cmd)}")

            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,  # merge stderr into the same log
                    start_new_session=True,
                    cwd=str(Path(__file__).resolve().parent.parent),
                )
            finally:
                # We close our handle — subprocess holds its own fd
                if hasattr(log_handle, "close"):
                    try:
                        log_handle.close()
                    except Exception:
                        pass

            logger.info(f"Server process started with PID {process.pid}")

            # Wait for server to be ready — with crash detection
            try:
                wait_for_server(
                    host,
                    port,
                    timeout=startup_timeout,
                    subprocess_handle=process,
                )
            except TimeoutError as e:
                # Surface the startup log tail in the error
                tail = _tail_file(startup_log, max_lines=40)
                raise TimeoutError(
                    f"{e}\n\n--- server startup log tail ({startup_log}) ---\n{tail}\n"
                    f"--- end startup log ---"
                ) from e
            except RuntimeError as e:
                # Server process died; include log
                tail = _tail_file(startup_log, max_lines=40)
                raise RuntimeError(
                    f"{e}\n\n--- server startup log tail ({startup_log}) ---\n{tail}\n"
                    f"--- end startup log ---"
                ) from e

            logger.info("Server started successfully")

    except TimeoutError as e:
        logger.error(f"Server startup failed (timeout): {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise


def wait_for_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: int = 30,
    subprocess_handle: Optional[subprocess.Popen] = None,
):
    """Wait for /api/health to respond. Bails out early if the subprocess dies."""
    logger.info(f"Waiting for server to be ready (timeout: {timeout}s)...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        # If we have a handle to the subprocess, detect crashes immediately
        if subprocess_handle is not None:
            rc = subprocess_handle.poll()
            if rc is not None:
                raise RuntimeError(
                    f"Server process exited during startup with code {rc}"
                )

        try:
            response = httpx.get(f"http://{host}:{port}/api/health", timeout=2.0)
            if response.status_code == 200:
                logger.info("Server is ready")
                return
        except Exception:
            pass

        time.sleep(0.5)

    raise TimeoutError(f"Server did not become ready within {timeout}s")


# ----------------------------------------------------------------------
# Stop / stats
# ----------------------------------------------------------------------
def stop_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: Path = DEFAULT_PID_FILE,
):
    logger.info("Stopping server...")
    try:
        try:
            response = httpx.post(
                f"http://{host}:{port}/api/shutdown",
                timeout=5.0,
            )
            if response.status_code == 200:
                logger.info("Server shutdown initiated via API")
                for _ in range(10):
                    if not is_server_running(host, port, pid_file):
                        logger.info("Server stopped successfully")
                        return
                    time.sleep(1)
        except Exception as e:
            logger.debug(f"Could not shutdown via API: {e}")

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if psutil.pid_exists(pid) and _pid_is_our_server(pid):
                    proc = psutil.Process(pid)
                    proc.terminate()
                    proc.wait(timeout=10)
                    logger.info(f"Server process {pid} terminated")
                pid_file.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Error killing server process: {e}")
    except Exception as e:
        logger.error(f"Error stopping server: {e}", exc_info=True)


def get_server_config(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> dict:
    """Fetch the server's /api/config snapshot (or an error dict)."""
    try:
        response = httpx.get(f"http://{host}:{port}/api/config", timeout=5.0)
        if response.status_code == 200:
            return response.json()
        return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def get_server_stats(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> dict:
    try:
        response = httpx.get(f"http://{host}:{port}/api/stats", timeout=5.0)
        if response.status_code == 200:
            return response.json()
        return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}
