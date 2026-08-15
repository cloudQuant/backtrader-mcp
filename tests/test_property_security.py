from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backtrader_mcp.contracts import StrategySpec
from backtrader_mcp.errors import Forbidden, InvalidRequest
from backtrader_mcp.security import TokenSigner, confined_path
from backtrader_mcp.state import StateStore


def _fresh_signer() -> tuple[TokenSigner, str]:
    root = tempfile.mkdtemp(prefix="property-signer-")
    return TokenSigner(Path(root), state=StateStore(Path(root))), root


@given(st.integers(min_value=0, max_value=200))
@settings(max_examples=40, deadline=None)
def test_any_single_byte_tamper_is_rejected(position):
    signer, root = _fresh_signer()
    try:
        token = signer.issue("change", {"change_id": "c1"})
        mutated = bytearray(token.encode("ascii"))
        position %= len(mutated)
        mutated[position] = (mutated[position] + 1) % 256
        with pytest.raises(Forbidden):
            signer.verify(mutated.decode("ascii", errors="replace"), "change")
    finally:
        shutil.rmtree(root, ignore_errors=True)


@given(st.text(alphabet="abc./\\", max_size=12))
@settings(max_examples=100, deadline=None)
def test_path_confinement_rejects_traversal(relative):
    root = Path(tempfile.mkdtemp(prefix="property-path-"))
    try:
        (root / "file.csv").write_text("x", encoding="utf-8")
        try:
            resolved = confined_path(root, relative, must_exist=False)
        except Forbidden:
            return
        assert resolved.is_relative_to(root.resolve())
    finally:
        shutil.rmtree(root, ignore_errors=True)


@given(
    st.dictionaries(
        st.text(max_size=8),
        st.recursive(
            st.none() | st.booleans(),
            lambda children: (
                st.lists(children, max_size=3)
                | st.dictionaries(st.text(max_size=4), children, max_size=3)
            ),
            max_leaves=12,
        ),
        max_size=8,
    )
)
@settings(max_examples=60, deadline=None)
def test_strategy_spec_parse_never_crashes(payload):
    """Arbitrary JSON-shaped input must yield a valid spec or a stable error."""
    if isinstance(payload, dict) and "spec_version" not in payload:
        payload = {**payload, "spec_version": "strategy-spec-v1"}
    try:
        spec = StrategySpec.parse(payload)
    except (InvalidRequest, TypeError, ValueError, KeyError):
        return
    assert isinstance(spec.as_dict(), dict)
    assert spec.archetype
