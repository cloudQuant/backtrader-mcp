from __future__ import annotations

import importlib
from pathlib import Path

import conftest
import pytest


def _runtime(root: Path) -> Path:
    package = root / "backtrader"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    return root


def test_explicit_test_runtime_root_takes_precedence(monkeypatch, tmp_path):
    runtime = _runtime(tmp_path / "explicit")
    monkeypatch.setenv("BACKTRADER_MCP_TEST_RUNTIME_ROOT", str(runtime))
    monkeypatch.setattr(conftest, "require_cloudquant_runtime", lambda root: root.resolve())
    assert conftest._backtrader_runtime_root() == runtime.resolve()


def test_invalid_explicit_test_runtime_root_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTRADER_MCP_TEST_RUNTIME_ROOT", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="BACKTRADER_MCP_TEST_RUNTIME_ROOT"):
        conftest._backtrader_runtime_root()


def test_untrusted_explicit_test_runtime_root_is_rejected(monkeypatch, tmp_path):
    runtime = _runtime(tmp_path / "untrusted")
    monkeypatch.setenv("BACKTRADER_MCP_TEST_RUNTIME_ROOT", str(runtime))

    with pytest.raises(RuntimeError, match="cloudQuant/backtrader"):
        conftest._backtrader_runtime_root()


def test_installed_backtrader_is_used_without_a_sibling_checkout(monkeypatch, tmp_path):
    module = importlib.import_module("backtrader")
    expected = Path(module.__file__).resolve().parent.parent
    monkeypatch.delenv("BACKTRADER_MCP_TEST_RUNTIME_ROOT", raising=False)
    monkeypatch.setattr(conftest, "REPOSITORY_ROOT", tmp_path)
    assert conftest._backtrader_runtime_root() == expected
