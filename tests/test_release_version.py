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

    assert BacktraderMCPService(settings).product_info()["version"] == __version__
    assert doctor_report(settings)["product"]["version"] == __version__


def test_mcp_server_reads_the_package_version_instead_of_a_literal():
    server_source = (REPOSITORY_ROOT / "src" / "backtrader_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    assert "from . import __version__" in server_source
    assert "version=__version__" in server_source


def test_changelog_latest_release_matches_package_version():
    """The most recent released CHANGELOG entry must equal __version__."""
    changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.findall(r"(?m)^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", changelog)
    assert released, "CHANGELOG has no versioned release entries"
    assert released[0] == __version__, (
        f"CHANGELOG latest release {released[0]} != package version {__version__}"
    )


def test_requires_python_has_an_upper_bound():
    project = _project_section()
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', project)
    assert match is not None
    assert match.group(1) == ">=3.10,<3.14"


def test_constraints_fall_inside_pyproject_ranges():
    """Every pinned constraint must satisfy the declared dependency range."""
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    constraints = (REPOSITORY_ROOT / "constraints" / "requirements-v2.txt").read_text(
        encoding="utf-8"
    )
    ranges = {
        name: spec
        for name, spec in re.findall(r'^"?([\w-]+)"?\s*=\s*\[?"?([^"\]]+)"?\]?', pyproject, re.M)
        if name in {"mcp", "pandas"}
    }
    pins = {}
    for name, version in re.findall(r"(?m)^([\w-]+)==([0-9][^;]*)", constraints):
        # Environment-marker lines may pin two versions; keep the first.
        pins.setdefault(name, version)
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    for name, spec in ranges.items():
        assert name in pins, f"{name} missing from constraints"
        assert SpecifierSet(spec.replace('"', "")).contains(Version(pins[name])), (
            f"{name} pin {pins[name]} outside declared range {spec}"
        )
