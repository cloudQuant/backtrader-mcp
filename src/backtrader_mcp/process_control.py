"""Platform-aware process group, environment, and termination helpers."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable, Mapping
from typing import Any


def _platform_name() -> str:
    return os.name


def is_posix() -> bool:
    return _platform_name() == "posix"


def popen_group_options(*, preexec_fn: Callable[[], None] | None = None) -> dict[str, Any]:
    """Return only Popen group options supported by the active platform."""

    if is_posix():
        options: dict[str, Any] = {"start_new_session": True}
        if preexec_fn is not None:
            options["preexec_fn"] = preexec_fn
        return options
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": creationflags} if creationflags else {}


def platform_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Preserve the minimum Windows launch variable without broad inheritance."""

    result = dict(environment)
    if not is_posix():
        system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if system_root:
            result.setdefault("SystemRoot", system_root)
    return result


def terminate_popen(process: subprocess.Popen[Any]) -> None:
    """Terminate a known child, escalating after a short bounded wait."""

    if process.poll() is not None:
        return
    if is_posix():
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        return
    try:
        process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def terminate_pid(pid: int) -> None:
    """Request termination for an already-recorded supervisor or child PID."""

    try:
        if is_posix():
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
