"""Restart and update — hot restart / hot upgrade for cc-feishu-bridge."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from cc_feishu_bridge.feishu.client import FeishuClient


class RestartError(Exception): pass
class StartupTimeoutError(RestartError): pass


# Step labels for CLI display (short, single line)
_CLI_STEP_LABELS = [
    "准备重启",
    "启动新 bridge",
    "等待新进程就绪",
    "重启完成",
]

# Step labels for Feishu messages (detailed, emoji)
_FEISHU_STEP_LABELS = [
    "🛑 准备重启",
    "🚀 启动新 bridge",
    "⏳ 等待新进程就绪",
    "✅ 重启完成",
]


@dataclass
class RestartStep:
    """A single step in the restart process, yielded as it happens."""
    step: int          # 1–4
    total: int         # always 4
    label: str         # short label shown to user
    status: str        # "done" | "error" | "final"
    detail: str = ""   # extra info (PID, path, etc.)
    success: bool = False   # True only on the final step on success
    new_pid: Optional[int] = None  # available on the final step


@dataclass
class RestartResult:
    success: bool
    new_pid: Optional[int] = None


def _pid_file_path(project_path: str) -> str:
    """Return the PID file path for a project."""
    return os.path.join(project_path, ".cc-feishu-bridge", "cc-feishu-bridge.pid")


def _read_pid(pid_file: str) -> Optional[int]:
    """Read PID from file. Returns None if file doesn't exist or is invalid."""
    if not os.path.exists(pid_file):
        return None
    try:
        return int(Path(pid_file).read_text().strip())
    except (ValueError, OSError):
        return None


def _is_process_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_process(pid: int, sig: int, timeout: float) -> bool:
    """Send signal to process and wait for it to die. Returns True if process stopped."""
    try:
        os.kill(pid, sig)
    except OSError:
        return True  # Process already dead

    # Wait for process to die
    start = time.time()
    while time.time() - start < timeout:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.1)
    return False


def _stop_bridge(project_path: str) -> bool:
    """Stop the bridge for a project. Uses SIGTERM then SIGKILL. Returns True if stopped, False if failed."""
    pid_file = _pid_file_path(project_path)
    pid = _read_pid(pid_file)

    if pid is None:
        return True  # Already stopped

    # SIGTERM first
    if not _kill_process(pid, signal.SIGTERM, timeout=5.0):
        # SIGKILL if still alive
        if not _kill_process(pid, signal.SIGKILL, timeout=2.0):
            return False

    # Clean up pid file
    try:
        Path(pid_file).unlink(missing_ok=True)
    except OSError:
        pass
    return True


def _start_bridge(project_path: str, timeout: float = 8.0) -> int:
    """Start the bridge for project using subprocess.Popen with start_new_session=True.

    Returns the PID of the started process.
    Raises StartupTimeoutError if pid file doesn't appear within timeout.
    """
    pid_file = _pid_file_path(project_path)

    # Remove stale pid file if exists
    Path(pid_file).unlink(missing_ok=True)

    # Start bridge via the installed binary (works for both pip installs and
    # PyInstaller binaries — cc-feishu-bridge is in PATH in both cases)
    project_cc = os.path.join(project_path, ".cc-feishu-bridge")
    stdout_log = open(os.path.join(project_cc, "bridge-stdout.log"), "w")
    stderr_log = open(os.path.join(project_cc, "bridge-stderr.log"), "w")
    try:
        proc = subprocess.Popen(
            ["cc-feishu-bridge", "start"],
            cwd=project_path,
            stdout=stdout_log,
            stderr=stderr_log,
            start_new_session=True,
        )

        # Wait for pid file to appear
        start = time.time()
        while time.time() - start < timeout:
            pid = _read_pid(pid_file)
            if pid is not None:
                stdout_log.close()
                stderr_log.close()
                return pid
            # Check if process crashed
            if proc.poll() is not None:
                stdout_log.close()
                stderr_log.close()
                raise StartupTimeoutError(f"Bridge process exited unexpectedly during startup")
            time.sleep(0.2)

        stdout_log.close()
        stderr_log.close()
        raise StartupTimeoutError(
            f"PID file did not appear within {timeout}s after starting bridge"
        )
    except Exception:
        stdout_log.close()
        stderr_log.close()
        raise
