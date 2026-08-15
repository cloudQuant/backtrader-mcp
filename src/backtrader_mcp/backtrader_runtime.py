"""CloudQuant Backtrader provenance policy and controlled installation."""

from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .errors import InvalidRequest

CLOUDQUANT_BACKTRADER_REPOSITORY = "https://github.com/cloudQuant/backtrader.git"
CLOUDQUANT_BACKTRADER_REPOSITORY_ID = "github.com/cloudquant/backtrader"
CLOUDQUANT_BACKTRADER_REVISION = "3c967ed61be184c0099ba5bef55d4bed09ad0b4a"
CLOUDQUANT_BACKTRADER_REQUIREMENT = (
    f"backtrader @ git+{CLOUDQUANT_BACKTRADER_REPOSITORY}@{CLOUDQUANT_BACKTRADER_REVISION}"
)


def _git_value(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _git_remote_url(root: Path) -> str | None:
    return _git_value(root, "remote", "get-url", "origin")


def _repository_id(url: str | None) -> str | None:
    """Return a credential-free GitHub repository identifier from a Git URL."""

    if not isinstance(url, str) or not url.strip():
        return None
    value = url.strip()
    if value.startswith("git+"):
        value = value[4:]
    if value.startswith("git@") and ":" in value:
        location = value.split("@", 1)[1]
        host, path = location.split(":", 1)
    else:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        path = parsed.path
    if host.lower() != "github.com":
        return None
    normalized_path = path.strip("/")
    if "@" in normalized_path:
        normalized_path = normalized_path.rsplit("@", 1)[0]
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]
    if not normalized_path:
        return None
    return f"github.com/{normalized_path.lower()}"


def _file_url_path(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        return None
    return Path(unquote(parsed.path)).resolve(strict=False)


def _package_root(package_file: Path) -> Path:
    return package_file.expanduser().resolve(strict=False).parent.parent


def _identity(
    *,
    installed: bool,
    root: Path | None,
    version: str | None,
    repository: str | None,
    provenance: str,
) -> dict[str, Any]:
    package_marker = root is not None and (root / "backtrader" / "__init__.py").is_file()
    trusted = package_marker and repository == CLOUDQUANT_BACKTRADER_REPOSITORY_ID
    if not installed:
        reason = "backtrader is not installed"
    elif not package_marker:
        reason = "backtrader does not expose backtrader/__init__.py"
    elif repository is None:
        reason = "Backtrader source provenance is unavailable"
    elif not trusted:
        reason = "Backtrader does not originate from cloudQuant/backtrader"
    else:
        reason = None
    return {
        "installed": installed,
        "trusted": trusted,
        "root": str(root) if root is not None else None,
        "package_marker": package_marker,
        "version": version,
        "repository": repository,
        "provenance": provenance,
        "reason": reason,
    }


def _distribution_direct_url(distribution: metadata.Distribution) -> tuple[str | None, str]:
    raw = distribution.read_text("direct_url.json")
    if not raw:
        return None, "unavailable"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "unavailable"
    url = payload.get("url")
    if not isinstance(url, str):
        return None, "unavailable"
    source_root = _file_url_path(url)
    if source_root is not None:
        return _repository_id(_git_remote_url(source_root)), "direct_url_file"
    provenance = "direct_url_vcs" if isinstance(payload.get("vcs_info"), dict) else "direct_url"
    return _repository_id(url), provenance


def _installed_from_distribution() -> dict[str, Any] | None:
    try:
        distribution = metadata.distribution("backtrader")
    except metadata.PackageNotFoundError:
        return None
    package_file = Path(str(distribution.locate_file("backtrader/__init__.py")))
    root = _package_root(package_file)
    repository, provenance = _distribution_direct_url(distribution)
    if repository is None:
        repository = _repository_id(_git_remote_url(root))
        if repository is not None:
            provenance = "package_git"
    return _identity(
        installed=True,
        root=root,
        version=distribution.version,
        repository=repository,
        provenance=provenance,
    )


def _installed_from_import_path() -> dict[str, Any] | None:
    spec = importlib.util.find_spec("backtrader")
    origin = spec.origin if spec is not None else None
    if not isinstance(origin, str):
        return None
    package_file = Path(origin)
    root = _package_root(package_file)
    return _identity(
        installed=True,
        root=root,
        version=None,
        repository=_repository_id(_git_remote_url(root)),
        provenance="package_git",
    )


def inspect_installed_backtrader() -> dict[str, Any]:
    """Inspect the active interpreter without importing Backtrader itself."""

    return (
        _installed_from_distribution()
        or _installed_from_import_path()
        or _identity(
            installed=False,
            root=None,
            version=None,
            repository=None,
            provenance="unavailable",
        )
    )


def inspect_runtime_root(root: Path) -> dict[str, Any]:
    """Inspect a registered runtime root and verify its CloudQuant provenance."""

    resolved = root.expanduser().resolve(strict=False)
    repository = _repository_id(_git_remote_url(resolved))
    provenance = "git_remote" if repository is not None else "unavailable"
    installed = inspect_installed_backtrader()
    if installed["root"] == str(resolved):
        # A registered root that IS the active installed package must be judged
        # by its distribution provenance (direct_url.json or the source
        # checkout's origin). A ``git -C`` probe can instead discover an
        # unrelated enclosing repository, e.g. a venv nested inside the product
        # checkout, and misidentify the runtime.
        repository_value = installed["repository"]
        repository = repository_value if isinstance(repository_value, str) else repository
        provenance_value = installed["provenance"]
        provenance = provenance_value if isinstance(provenance_value, str) else provenance
    return _identity(
        installed=resolved.is_dir(),
        root=resolved,
        version=None,
        repository=repository,
        provenance=provenance,
    )


def require_cloudquant_runtime(root: Path) -> Path:
    """Return a trusted runtime root or reject a non-CloudQuant Backtrader."""

    identity = inspect_runtime_root(root)
    if not identity["trusted"]:
        reason = identity["reason"] or "unknown provenance error"
        raise InvalidRequest(
            f"registered Backtrader runtime must originate from cloudQuant/backtrader: {reason}"
        )
    return root.expanduser().resolve(strict=True)


def ensure_cloudquant_backtrader() -> dict[str, Any]:
    """Install the pinned CloudQuant distribution only when Backtrader is absent."""

    before = inspect_installed_backtrader()
    if before["trusted"]:
        return {"status": "passed", "action": "already_installed", "runtime": before}
    if before["installed"]:
        warning = {
            "code": "installed_backtrader_untrusted",
            "message": "an installed Backtrader is not cloudQuant/backtrader; it was not overwritten",
            "suggestion": "remove it explicitly, then rerun backtrader-mcp install-backtrader",
        }
        return {
            "status": "warning",
            "action": "warning_existing_untrusted",
            "runtime": before,
            "warning": warning,
        }
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        CLOUDQUANT_BACKTRADER_REQUIREMENT,
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "failed",
            "action": "install_failed",
            "runtime": inspect_installed_backtrader(),
            "install": {"command": command, "error": f"{type(exc).__name__}: {exc}"},
        }
    after = inspect_installed_backtrader()
    if completed.returncode == 0 and after["trusted"]:
        return {
            "status": "passed",
            "action": "installed",
            "runtime": after,
            "install": {"command": command, "returncode": completed.returncode},
        }
    return {
        "status": "failed",
        "action": "install_failed",
        "runtime": after,
        "install": {
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        },
    }
