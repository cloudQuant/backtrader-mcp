from __future__ import annotations

from pathlib import Path

from backtrader_mcp.audit import audit_independence


def _write_module(root: Path, content: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "module.py").write_text(content, encoding="utf-8")


def test_audit_independence_accepts_a_clean_package(tmp_path: Path):
    root = tmp_path / "package"
    _write_module(root, "from . import sibling\n")

    report = audit_independence(root)

    assert report["status"] == "passed"
    assert report["files_checked"] == 1
    assert report["findings"] == []
    assert report["assertions"] == [
        "no sibling product imports",
        "no parent-relative imports",
        "no eval or exec calls",
        "candidate modules are only launched by the controlled worker",
    ]


def test_audit_independence_reports_sibling_product_import(tmp_path: Path):
    root = tmp_path / "package"
    _write_module(root, "import backtrader_agent.runtime\n")

    report = audit_independence(root)

    assert report["status"] == "failed"
    assert report["findings"] == [
        {
            "path": "module.py",
            "line": 1,
            "code": "sibling_product_import",
            "module": "backtrader_agent.runtime",
        }
    ]


def test_audit_independence_reports_parent_relative_import(tmp_path: Path):
    root = tmp_path / "package"
    _write_module(root, "from ..shared import value\n")

    report = audit_independence(root)

    assert report["status"] == "failed"
    assert report["findings"] == [
        {
            "path": "module.py",
            "line": 1,
            "code": "parent_relative_import",
        }
    ]


def test_audit_independence_reports_dynamic_execution(tmp_path: Path):
    root = tmp_path / "package"
    _write_module(root, 'exec("value = 1")\n')

    report = audit_independence(root)

    assert report["status"] == "failed"
    assert report["findings"] == [
        {
            "path": "module.py",
            "line": 1,
            "code": "dynamic_execution",
            "call": "exec",
        }
    ]
