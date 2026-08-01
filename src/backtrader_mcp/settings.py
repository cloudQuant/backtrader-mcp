"""Trusted local configuration loaded at process start."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import InvalidRequest


def _root_map(raw: str | None) -> dict[str, Path]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidRequest("root maps must be valid JSON objects") from exc
    if not isinstance(value, dict):
        raise InvalidRequest("root maps must be JSON objects")
    result: dict[str, Path] = {}
    for key, path in value.items():
        if not isinstance(key, str) or not key.replace("_", "").replace("-", "").isalnum():
            raise InvalidRequest(f"invalid root id: {key!r}")
        candidate = Path(path).expanduser().resolve(strict=False)
        result[key] = candidate
    return result


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidRequest(f"{name} must be a positive integer") from exc
    if value < 1:
        raise InvalidRequest(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidRequest(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise InvalidRequest(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class Settings:
    state_root: Path
    source_roots: dict[str, Path] = field(default_factory=dict)
    target_roots: dict[str, Path] = field(default_factory=dict)
    runtimes: dict[str, Path] = field(default_factory=dict)
    max_dataset_bytes: int = 64 * 1024 * 1024
    max_preview_rows: int = 200
    max_run_seconds: int = 300
    # Candidate subprocess resource caps. ``max_run_cpu_seconds=0`` means
    # "derive from max_run_seconds plus a 30s buffer" at run time.
    max_run_cpu_seconds: int = 0
    max_run_memory_bytes: int = 2 * 1024 * 1024 * 1024
    max_run_file_size_bytes: int = 256 * 1024 * 1024
    max_run_processes: int = 8
    max_concurrent_jobs: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        state = Path(
            os.environ.get(
                "BACKTRADER_MCP_STATE_ROOT",
                str(Path.home() / ".local" / "share" / "backtrader-mcp"),
            )
        ).expanduser()
        return cls(
            state_root=state.resolve(strict=False),
            source_roots=_root_map(os.environ.get("BACKTRADER_MCP_SOURCE_ROOTS")),
            target_roots=_root_map(os.environ.get("BACKTRADER_MCP_TARGET_ROOTS")),
            runtimes=_root_map(os.environ.get("BACKTRADER_MCP_RUNTIMES")),
            max_dataset_bytes=_positive_int(
                "BACKTRADER_MCP_MAX_DATASET_BYTES",
                64 * 1024 * 1024,
            ),
            max_preview_rows=_positive_int("BACKTRADER_MCP_MAX_PREVIEW_ROWS", 200),
            max_run_seconds=_positive_int("BACKTRADER_MCP_MAX_RUN_SECONDS", 300),
            max_run_cpu_seconds=_non_negative_int("BACKTRADER_MCP_MAX_RUN_CPU_SECONDS", 0),
            max_run_memory_bytes=_positive_int(
                "BACKTRADER_MCP_MAX_RUN_MEMORY_BYTES",
                2 * 1024 * 1024 * 1024,
            ),
            max_run_file_size_bytes=_positive_int(
                "BACKTRADER_MCP_MAX_RUN_FILE_SIZE_BYTES",
                256 * 1024 * 1024,
            ),
            max_run_processes=_positive_int("BACKTRADER_MCP_MAX_RUN_PROCESSES", 8),
            max_concurrent_jobs=_positive_int("BACKTRADER_MCP_MAX_CONCURRENT_JOBS", 4),
        )

    def initialize(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_root, 0o700)
        for child in ("cas", "drafts", "jobs", "locks", "transactions"):
            (self.state_root / child).mkdir(parents=True, exist_ok=True, mode=0o700)

    def resource_limits(self) -> dict[str, int]:
        """Frozen candidate subprocess resource limits for one run."""
        cpu = self.max_run_cpu_seconds or (self.max_run_seconds + 30)
        return {
            "cpu_seconds": cpu,
            "memory_bytes": self.max_run_memory_bytes,
            "file_size_bytes": self.max_run_file_size_bytes,
            "processes": self.max_run_processes,
        }
