"""Project switcher — stops current bridge, starts target bridge with rewritten config."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


class SwitchError(Exception): pass
class NotInitializedError(SwitchError): pass
class TargetStopError(SwitchError): pass
class CurrentStopError(SwitchError): pass
class StartupTimeoutError(SwitchError): pass


@dataclass
class SwitchStep:
    """A single step in the switch process, yielded as it happens."""
    step: int          # 1–5
    total: int         # always 5
    label: str         # short label shown to user
    status: str        # "done" | "error" | "final"
    detail: str = ""   # extra info (PID, path, etc.)
    success: bool = False   # True only on the final step on success
    target_pid: Optional[int] = None  # available on the final step


@dataclass
class SwitchResult:
    success: bool
    target_path: str
    target_pid: Optional[int] = None


def _pid_file_path(project_path: str) -> str:
    """Return the PID file path for a project."""
    return os.path.join(project_path, ".cc-feishu-bridge", "cc-feishu-bridge.pid")


def _config_file_path(project_path: str) -> str:
    """Return the config file path for a project."""
    return os.path.join(project_path, ".cc-feishu-bridge", "config.yaml")


def _target_config_file_path(project_path: str) -> str:
    """Return the target config file path (where we write the copied config)."""
    return _config_file_path(project_path)


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



def _copy_and_fix_config(current_path: str, target_path: str) -> None:
    """Read current config.yaml, rewrite storage.db_path to target's sessions.db, write to target."""
    current_config_path = _config_file_path(current_path)
    target_config_path = _target_config_file_path(target_path)

    if not os.path.exists(current_config_path):
        raise SwitchError("当前项目未初始化（无 config.yaml）")

    with open(current_config_path) as f:
        raw = yaml.safe_load(f)

    # Rewrite storage.db_path to target's sessions.db
    target_sessions_db = os.path.join(
        target_path, ".cc-feishu-bridge", "sessions.db"
    )
    if "storage" not in raw:
        raw["storage"] = {}
    raw["storage"]["db_path"] = target_sessions_db

    # Ensure .cc-feishu-bridge dir exists in target
    Path(target_config_path).parent.mkdir(parents=True, exist_ok=True)

    with open(target_config_path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)


def _start_bridge(target_path: str, timeout: float = 8.0) -> int:
    """Start the bridge for target project using subprocess.Popen with start_new_session=True.

    Returns the PID of the started process.
    Raises StartupTimeoutError if pid file doesn't appear within timeout.
    """
    pid_file = _pid_file_path(target_path)

    # Remove stale pid file if exists
    Path(pid_file).unlink(missing_ok=True)

    # Start bridge via the installed binary (works for both pip installs and
    # PyInstaller binaries — cc-feishu-bridge is in PATH in both cases)
    target_cc = os.path.join(target_path, ".cc-feishu-bridge")
    stdout_log = open(os.path.join(target_cc, "bridge-stdout.log"), "w")
    stderr_log = open(os.path.join(target_cc, "bridge-stderr.log"), "w")
    proc = subprocess.Popen(
        ["cc-feishu-bridge", "start"],
        cwd=target_path,
        stdout=stdout_log,
        stderr=stderr_log,
        start_new_session=True,
    )

    # Wait for pid file to appear
    start = time.time()
    while time.time() - start < timeout:
        pid = _read_pid(pid_file)
        if pid is not None:
            return pid
        # Check if process crashed
        if proc.poll() is not None:
            raise StartupTimeoutError(f"Bridge process exited unexpectedly during startup")
        time.sleep(0.2)

    raise StartupTimeoutError(
        f"PID file did not appear within {timeout}s after starting bridge"
    )


def switch_to(target_path: str):
    """Execute the full project switch flow, yielding SwitchStep as each step completes.

    Steps (stops on error, no rollback):
    1. Stop target bridge (if running)
    2. Copy config.yaml to target (rewrite storage.db_path)
    3. Start bridge in target
    4. Verify target bridge is running
    5. Stop current bridge

    Yields SwitchStep for each step. Caller prints/logs/sends Feishu messages.
    Raises SwitchError on fatal failure.
    """
    current_path = os.getcwd()

    # Step 1: Stop target bridge
    yield SwitchStep(step=1, total=5, label="停止目标 bridge", status="done")
    if not _stop_bridge(target_path):
        raise TargetStopError(f"无法停止目标 bridge")

    # Step 2: Copy and fix config.yaml
    yield SwitchStep(step=2, total=5, label="拷贝配置文件", status="done")
    try:
        _copy_and_fix_config(current_path, target_path)
    except Exception as e:
        raise SwitchError(f"无法拷贝配置文件到目标: {e}")

    # Step 3: Start target bridge
    yield SwitchStep(step=3, total=5, label="启动目标 bridge", status="done")
    target_pid: Optional[int] = None
    try:
        target_pid = _start_bridge(target_path)
    except StartupTimeoutError as e:
        raise StartupTimeoutError(f"目标 bridge 启动超时: {e}")

    # Step 4: Verify target bridge is running
    yield SwitchStep(step=4, total=5, label="确认目标 bridge 运行中", status="done", detail=f"PID {target_pid}")

    # Step 5: Stop current bridge
    yield SwitchStep(step=5, total=5, label="停止当前 bridge", status="done")
    if not _stop_bridge(current_path):
        raise CurrentStopError(f"无法停止当前 bridge")

    yield SwitchStep(step=5, total=5, label="切换完成", status="final",
                     detail=f"新 bridge PID {target_pid}", success=True, target_pid=target_pid)

    return SwitchResult(success=True, target_path=target_path, target_pid=target_pid)