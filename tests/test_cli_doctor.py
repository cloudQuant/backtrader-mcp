from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import backtrader_mcp.doctor as doctor_module
from backtrader_mcp.backtrader_runtime import inspect_installed_backtrader
from backtrader_mcp.cli import main


def _installed_cloudquant_runtime_root() -> Path:
    """Return the package root installed from the pinned CloudQuant dependency.

    Doctor CLI tests must not depend on a developer's sibling checkout: the CI
    environment deliberately exercises an isolated, installed distribution.
    """

    installed = inspect_installed_backtrader()
    root = installed["root"]
    assert installed["trusted"] is True, installed
    assert isinstance(root, str), installed
    return Path(root)


def _tree_snapshot(root: Path) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    directories = tuple(
        sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_dir())
    )
    files = tuple(
        sorted(
            (
                str(path.relative_to(root)),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in root.rglob("*")
            if path.is_file()
        )
    )
    return directories, files


def _create_synthetic_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    package = runtime / "backtrader"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "__version__ = '1.3.0'\n"
        "class Cerebro: pass\n"
        "class Strategy: pass\n"
        "class GenericCSVData: pass\n"
        "class PandasData: pass\n"
        "class Feeds:\n"
        "    pass\n"
        "feeds = Feeds()\n"
        "feeds.GenericCSVData = GenericCSVData\n"
        "feeds.PandasData = PandasData\n",
        encoding="utf-8",
    )
    return runtime


def _supported_distributions(monkeypatch) -> None:
    versions = {
        "backtrader-mcp": "0.2.0",
        "mcp": "2.0.0",
        "pandas": "2.2.3",
    }
    monkeypatch.setattr(doctor_module.metadata, "version", versions.__getitem__)


def _configure_roots(monkeypatch, tmp_path: Path, *, runtimes: dict[str, str]) -> Path:
    state = tmp_path / "state"
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    monkeypatch.setenv("BACKTRADER_MCP_STATE_ROOT", str(state))
    monkeypatch.setenv("BACKTRADER_MCP_SOURCE_ROOTS", json.dumps({"market": str(source)}))
    monkeypatch.setenv("BACKTRADER_MCP_TARGET_ROOTS", json.dumps({"strategies": str(target)}))
    monkeypatch.setenv("BACKTRADER_MCP_RUNTIMES", json.dumps(runtimes))
    return state


def test_doctor_cli_reports_actual_runtime_without_mutating_state(monkeypatch, tmp_path, capsys):
    _supported_distributions(monkeypatch)
    installed = inspect_installed_backtrader()
    runtime_root = _installed_cloudquant_runtime_root()
    state = _configure_roots(
        monkeypatch,
        tmp_path,
        runtimes={"default": str(runtime_root)},
    )

    exit_code = main(["doctor"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0, report["issues"]
    assert captured.err == ""
    assert report["schema_version"] == "backtrader-mcp-doctor-v1"
    assert report["status"] == "passed"
    assert report["product"]["version"] == "0.2.0"
    assert report["product"]["dependencies"]["mcp"]["version"] == "2.0.0"
    runtime = report["runtimes"][0]
    assert runtime["runtime_id"] == "default"
    assert runtime["version"] == installed["version"]
    assert runtime["origin_matches_runtime"] is True
    assert Path(runtime["module_file"]).is_relative_to(runtime_root / "backtrader")
    assert runtime["capabilities"] == {
        "cerebro": True,
        "generic_csv": True,
        "pandas_data": True,
        "strategy": True,
    }
    assert report["capabilities"]["run_profiles"] == [
        "fixed_tests",
        "parameter_sweep",
        "runnext",
        "runonce",
        "runonce_runnext_compare",
    ]
    assert not state.exists(), "doctor must remain read-only"


def test_doctor_runtime_probe_uses_cloudquant_light_import(monkeypatch, tmp_path):
    runtime = _create_synthetic_runtime(tmp_path)
    monkeypatch.setattr(
        doctor_module,
        "inspect_runtime_root",
        lambda _: {
            "trusted": True,
            "package_marker": True,
            "repository": "github.com/cloudquant/backtrader",
            "provenance": "git_remote",
        },
    )
    monkeypatch.setattr(doctor_module, "_git_value", lambda *_: None)
    probe_environments: list[dict[str, str]] = []

    def probe(command, **kwargs):
        probe_environments.append(kwargs["env"])
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "module_file": str(runtime / "backtrader" / "__init__.py"),
                    "version": "1.3.0",
                    "capabilities": {
                        "cerebro": True,
                        "strategy": True,
                        "generic_csv": True,
                        "pandas_data": True,
                    },
                }
            ),
            "",
        )

    monkeypatch.setattr(doctor_module.subprocess, "run", probe)

    report, issues = doctor_module._runtime_report("default", runtime)

    assert report["status"] == "passed"
    assert issues == []
    assert len(probe_environments) == 1
    assert probe_environments[0]["BACKTRADER_LIGHT_IMPORT"] == "1"
    assert probe_environments[0]["PYTHONPATH"] == str(runtime)


def test_doctor_cli_does_not_write_any_configured_root_or_runtime(monkeypatch, tmp_path, capsys):
    _supported_distributions(monkeypatch)
    runtime = _create_synthetic_runtime(tmp_path)
    state = _configure_roots(
        monkeypatch,
        tmp_path,
        runtimes={"default": str(runtime)},
    )
    before = _tree_snapshot(tmp_path)

    exit_code = main(["doctor"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert any(issue["code"] == "runtime_untrusted_source" for issue in report["issues"])
    assert _tree_snapshot(tmp_path) == before
    assert not state.exists()
    assert not list(runtime.rglob("*.pyc"))
    assert not list(runtime.rglob("__pycache__"))


def test_doctor_warns_when_the_active_backtrader_is_not_cloudquant(monkeypatch, tmp_path, capsys):
    _supported_distributions(monkeypatch)
    runtime_root = _installed_cloudquant_runtime_root()
    _configure_roots(
        monkeypatch,
        tmp_path,
        runtimes={"default": str(runtime_root)},
    )
    monkeypatch.setattr(
        doctor_module,
        "inspect_installed_backtrader",
        lambda: {
            "installed": True,
            "trusted": False,
            "root": "/site-packages",
            "package_marker": True,
            "version": "1.9.78.123",
            "repository": "github.com/mementum/backtrader",
            "provenance": "direct_url_vcs",
            "reason": "Backtrader does not originate from cloudQuant/backtrader",
        },
    )

    exit_code = main(["doctor"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0, report["issues"]
    assert report["installed_backtrader"]["trusted"] is False
    assert any(issue["code"] == "installed_backtrader_untrusted" for issue in report["issues"])


def test_doctor_cli_fails_closed_when_runtime_is_not_configured(monkeypatch, tmp_path, capsys):
    _supported_distributions(monkeypatch)
    _configure_roots(monkeypatch, tmp_path, runtimes={})

    exit_code = main(["doctor"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert report["status"] == "failed"
    assert any(issue["code"] == "runtimes_empty" for issue in report["issues"])


def test_doctor_cli_returns_stable_error_for_invalid_root_json(monkeypatch, capsys):
    monkeypatch.setenv("BACKTRADER_MCP_RUNTIMES", "not-json")

    exit_code = main(["doctor"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "code": "invalid_request",
        "message": "root maps must be valid JSON objects",
    }


def test_doctor_cli_returns_stable_error_for_invalid_limit(monkeypatch, capsys):
    monkeypatch.setenv("BACKTRADER_MCP_MAX_RUN_SECONDS", "unbounded")

    exit_code = main(["doctor"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "code": "invalid_request",
        "message": "BACKTRADER_MCP_MAX_RUN_SECONDS must be a positive integer",
    }
