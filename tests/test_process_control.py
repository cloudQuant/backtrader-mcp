from __future__ import annotations

import signal
import subprocess

from backtrader_mcp import jobs as jobs_module
from backtrader_mcp import process_control


class _Process:
    pid = 123

    def __init__(self, *, wait_times_out: bool = False) -> None:
        self.wait_times_out = wait_times_out
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float | None] = []

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self.wait_times_out:
            raise subprocess.TimeoutExpired("candidate", timeout)
        return 0


def test_posix_popen_group_options_keep_session_and_candidate_preexec(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "posix")

    def preexec() -> None:
        return None

    assert process_control.popen_group_options(preexec_fn=preexec) == {
        "start_new_session": True,
        "preexec_fn": preexec,
    }
    assert process_control.popen_group_options() == {"start_new_session": True}


def test_non_posix_popen_group_options_exclude_posix_only_arguments(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "nt")
    monkeypatch.setattr(
        process_control.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False
    )

    assert process_control.popen_group_options(preexec_fn=lambda: None) == {"creationflags": 0x200}


def test_non_posix_environment_only_adds_system_root(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "nt")
    monkeypatch.setenv("SystemRoot", r"C:\\Windows")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-leak")

    assert process_control.platform_environment({"PATH": "safe", "PYTHONPATH": "trusted"}) == {
        "PATH": "safe",
        "PYTHONPATH": "trusted",
        "SystemRoot": r"C:\\Windows",
    }


def test_posix_environment_does_not_copy_system_root(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "posix")
    monkeypatch.setenv("SystemRoot", r"C:\\Windows")

    assert process_control.platform_environment({"PATH": "safe"}) == {"PATH": "safe"}


def test_non_posix_environment_accepts_uppercase_system_root(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "nt")
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.setenv("SYSTEMROOT", r"C:\\Windows")

    assert process_control.platform_environment({"PATH": "safe"}) == {
        "PATH": "safe",
        "SystemRoot": r"C:\\Windows",
    }


def test_non_posix_termination_uses_popen_methods_and_escalates(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "nt")
    process = _Process(wait_times_out=True)

    process_control.terminate_popen(process)

    assert process.terminate_calls == 1
    assert process.wait_calls == [2]
    assert process.kill_calls == 1


def test_posix_termination_uses_process_group_term_then_kill(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_control.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    process = _Process(wait_times_out=True)

    process_control.terminate_popen(process)

    assert calls == [(123, signal.SIGTERM), (123, signal.SIGKILL)]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_non_posix_pid_termination_does_not_call_killpg(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "nt")
    pid_calls: list[tuple[int, int]] = []
    group_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_control.os, "kill", lambda pid, sig: pid_calls.append((pid, sig)))
    monkeypatch.setattr(
        process_control.os,
        "killpg",
        lambda pid, sig: group_calls.append((pid, sig)),
    )

    process_control.terminate_pid(456)

    assert pid_calls == [(456, signal.SIGTERM)]
    assert group_calls == []


def test_posix_pid_termination_uses_killpg(monkeypatch):
    monkeypatch.setattr(process_control, "_platform_name", lambda: "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(process_control.os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    process_control.terminate_pid(456)

    assert calls == [(456, signal.SIGTERM)]


def test_non_posix_pid_liveness_does_not_call_waitpid(monkeypatch):
    monkeypatch.setattr(jobs_module, "is_posix", lambda: False, raising=False)
    monkeypatch.setattr(
        jobs_module.os,
        "waitpid",
        lambda *_: (_ for _ in ()).throw(AssertionError("waitpid is POSIX-only")),
    )
    monkeypatch.setattr(
        jobs_module.os,
        "kill",
        lambda *_: (_ for _ in ()).throw(AssertionError("signal-zero probing is unsafe")),
    )

    assert jobs_module._pid_alive(456) is True
