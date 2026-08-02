from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 uses the supported backport in test extras.
    import tomli as tomllib

import backtrader_mcp.backtrader_runtime as runtime_policy
import backtrader_mcp.settings as settings_module
from backtrader_mcp.errors import InvalidRequest
from backtrader_mcp.settings import Settings


def _runtime(root: Path) -> Path:
    package = root / "backtrader"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '1.3.0'\n", encoding="utf-8")
    (package / "version.py").write_text("__version__ = '1.3.0'\n", encoding="utf-8")
    return root


def test_runtime_root_accepts_only_the_cloudquant_repository(monkeypatch, tmp_path):
    root = _runtime(tmp_path / "runtime")
    monkeypatch.setattr(
        runtime_policy,
        "_git_remote_url",
        lambda _: "git@github.com:cloudQuant/backtrader.git",
    )

    trusted = runtime_policy.inspect_runtime_root(root)

    assert trusted["trusted"] is True
    assert trusted["repository"] == runtime_policy.CLOUDQUANT_BACKTRADER_REPOSITORY_ID
    assert trusted["provenance"] == "git_remote"

    monkeypatch.setattr(
        runtime_policy,
        "_git_remote_url",
        lambda _: "https://github.com/mementum/backtrader.git",
    )
    rejected = runtime_policy.inspect_runtime_root(root)

    assert rejected["trusted"] is False
    assert rejected["repository"] == "github.com/mementum/backtrader"
    with pytest.raises(InvalidRequest, match="cloudQuant/backtrader"):
        runtime_policy.require_cloudquant_runtime(root)


class _Distribution:
    version = "1.3.0"

    def __init__(self, site_root: Path, direct_url: str):
        self._site_root = site_root
        self._direct_url = direct_url

    def locate_file(self, path: str) -> Path:
        assert path == "backtrader/__init__.py"
        return self._site_root / path

    def read_text(self, path: str) -> str | None:
        return self._direct_url if path == "direct_url.json" else None


def test_installed_editable_cloudquant_distribution_is_trusted(monkeypatch, tmp_path):
    source = _runtime(tmp_path / "source")
    site_root = _runtime(tmp_path / "site")
    direct_url = json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})
    distribution = _Distribution(site_root, direct_url)
    monkeypatch.setattr(runtime_policy.metadata, "distribution", lambda _: distribution)
    monkeypatch.setattr(
        runtime_policy,
        "_git_remote_url",
        lambda root: (
            "https://github.com/cloudQuant/backtrader.git" if root == source.resolve() else None
        ),
    )

    installed = runtime_policy.inspect_installed_backtrader()

    assert installed["installed"] is True
    assert installed["trusted"] is True
    assert installed["root"] == str(site_root.resolve())
    assert installed["provenance"] == "direct_url_file"
    assert installed["repository"] == runtime_policy.CLOUDQUANT_BACKTRADER_REPOSITORY_ID


def test_ensure_warns_and_never_overwrites_an_untrusted_existing_distribution(monkeypatch):
    existing = {
        "installed": True,
        "trusted": False,
        "root": "/site-packages",
        "version": "1.9.78.123",
        "repository": "github.com/mementum/backtrader",
        "provenance": "direct_url_vcs",
        "reason": "installed Backtrader does not originate from cloudQuant/backtrader",
    }
    monkeypatch.setattr(runtime_policy, "inspect_installed_backtrader", lambda: existing)

    def unexpected_install(*args, **kwargs):
        raise AssertionError("an untrusted existing distribution must not be overwritten")

    monkeypatch.setattr(runtime_policy.subprocess, "run", unexpected_install)

    result = runtime_policy.ensure_cloudquant_backtrader()

    assert result["status"] == "warning"
    assert result["action"] == "warning_existing_untrusted"
    assert result["warning"]["code"] == "installed_backtrader_untrusted"


def test_ensure_installs_the_pinned_cloudquant_distribution_when_missing(monkeypatch):
    missing = {
        "installed": False,
        "trusted": False,
        "root": None,
        "version": None,
        "repository": None,
        "provenance": "unavailable",
        "reason": "backtrader is not installed",
    }
    installed = {
        **missing,
        "installed": True,
        "trusted": True,
        "root": "/site-packages",
        "version": "1.3.0",
        "repository": runtime_policy.CLOUDQUANT_BACKTRADER_REPOSITORY_ID,
        "provenance": "direct_url_vcs",
        "reason": None,
    }
    states = iter((missing, installed))
    monkeypatch.setattr(runtime_policy, "inspect_installed_backtrader", lambda: next(states))
    calls: list[list[str]] = []

    def install(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "installed", "")

    monkeypatch.setattr(runtime_policy.subprocess, "run", install)

    result = runtime_policy.ensure_cloudquant_backtrader()

    assert result["status"] == "passed"
    assert result["action"] == "installed"
    assert calls == [
        [
            runtime_policy.sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            runtime_policy.CLOUDQUANT_BACKTRADER_REQUIREMENT,
        ]
    ]


def test_settings_uses_a_trusted_installed_runtime_only_when_unconfigured(monkeypatch, tmp_path):
    discovered = {
        "installed": True,
        "trusted": True,
        "root": str(_runtime(tmp_path / "site").resolve()),
        "version": "1.3.0",
        "repository": runtime_policy.CLOUDQUANT_BACKTRADER_REPOSITORY_ID,
        "provenance": "direct_url_vcs",
        "reason": None,
    }
    monkeypatch.delenv("BACKTRADER_MCP_RUNTIMES", raising=False)
    monkeypatch.setattr(settings_module, "inspect_installed_backtrader", lambda: discovered)

    settings = Settings.from_env()

    assert settings.runtimes == {"default": Path(discovered["root"])}

    monkeypatch.setenv("BACKTRADER_MCP_RUNTIMES", "{}")
    assert Settings.from_env().runtimes == {}


def test_settings_does_not_register_an_untrusted_installed_runtime(monkeypatch):
    monkeypatch.delenv("BACKTRADER_MCP_RUNTIMES", raising=False)
    monkeypatch.setattr(
        settings_module,
        "inspect_installed_backtrader",
        lambda: {
            "installed": True,
            "trusted": False,
            "root": "/site-packages",
            "version": "1.9.78.123",
            "repository": "github.com/mementum/backtrader",
            "provenance": "direct_url_vcs",
            "reason": "Backtrader does not originate from cloudQuant/backtrader",
        },
    )

    assert Settings.from_env().runtimes == {}


def test_distribution_requires_the_pinned_cloudquant_backtrader_source():
    project_root = Path(__file__).resolve().parents[1]
    with (project_root / "pyproject.toml").open("rb") as handle:
        configuration = tomllib.load(handle)
    project = configuration["project"]

    assert runtime_policy.CLOUDQUANT_BACKTRADER_REQUIREMENT in project["dependencies"]
    assert not any(
        dependency.startswith("backtrader==")
        for dependency in project["optional-dependencies"]["test"]
    )
    assert configuration["tool"]["hatch"]["metadata"]["allow-direct-references"] is True
