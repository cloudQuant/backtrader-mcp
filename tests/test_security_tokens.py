"""Token lifecycle tests: expiry, kind mismatch, tampering, claim round-trip."""

from __future__ import annotations

import time

import pytest

from backtrader_mcp.errors import Forbidden
from backtrader_mcp.security import TokenSigner


def test_token_claims_roundtrip(tmp_path):
    signer = TokenSigner(tmp_path)
    token = signer.issue("run_plan", {"run_plan_id": "rp1", "run_plan_hash": "abc"})
    claims = signer.verify(token, "run_plan")
    assert claims["run_plan_id"] == "rp1"
    assert claims["run_plan_hash"] == "abc"


def test_token_expiry_rejected(tmp_path, monkeypatch):
    import backtrader_mcp.security as sec

    base = time.time()
    monkeypatch.setattr(sec.time, "time", lambda: base)
    signer = TokenSigner(tmp_path)
    token = signer.issue("validation", {"x": 1}, ttl_seconds=1)
    monkeypatch.setattr(sec.time, "time", lambda: base + 2)
    with pytest.raises(Forbidden, match="expired"):
        signer.verify(token, "validation")


def test_token_kind_mismatch_rejected(tmp_path):
    signer = TokenSigner(tmp_path)
    token = signer.issue("validation", {"x": 1})
    with pytest.raises(Forbidden, match="kind"):
        signer.verify(token, "change")


def test_token_tampering_rejected(tmp_path):
    signer = TokenSigner(tmp_path)
    token = signer.issue("validation", {"x": 1})
    # Flip the final characters of the signature so compare_digest fails.
    suffix = "AA" if not token.endswith("AA") else "BB"
    tampered = token[: -len(suffix)] + suffix
    with pytest.raises(Forbidden):
        signer.verify(tampered, "validation")


def test_token_secret_is_restricted(tmp_path):
    TokenSigner(tmp_path)
    mode = (tmp_path / "token-secret").stat().st_mode & 0o777
    assert mode == 0o600
