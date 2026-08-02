from __future__ import annotations

import re
from pathlib import Path

from backtrader_mcp import __version__
from backtrader_mcp.doctor import doctor_report
from backtrader_mcp.service import BacktraderMCPService
from backtrader_mcp.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _project_section() -> str:
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\[project\]\n(.*?)(?=^\[|\Z)", pyproject)
    assert match is not None
    return match.group(1)


def test_build_metadata_reads_the_package_version_source():
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dynamic = ["version"]' in _project_section()
    assert '[tool.hatch.version]\npath = "src/backtrader_mcp/__init__.py"' in pyproject


def test_runtime_version_surfaces_match_the_package_version(tmp_path: Path):
    settings = Settings(state_root=tmp_path / "state")

    assert __version__ == "0.2.0"
    assert BacktraderMCPService(settings).product_info()["version"] == __version__
    assert doctor_report(settings)["product"]["version"] == __version__


def test_mcp_server_reads_the_package_version_instead_of_a_literal():
    server_source = (REPOSITORY_ROOT / "src" / "backtrader_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    assert "from . import __version__" in server_source
    assert "version=__version__" in server_source
