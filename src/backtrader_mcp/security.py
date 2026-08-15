"""Path confinement, signed capability tokens, and local approvals."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from .errors import Conflict, Forbidden, InvalidRequest
from .util import atomic_write, canonical_json


def confined_path(root: Path, relative: str, *, must_exist: bool) -> Path:
    """Resolve a caller-relative path without allowing escape or symlink traversal."""
    value = Path(relative)
    if (
        value.is_absolute()
        or not value.parts
        or any(part in ("", ".", "..") for part in value.parts)
    ):
        raise Forbidden("path must be a normalized non-empty relative path")
    root = root.resolve(strict=True)
    current = root
    for part in value.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise Forbidden("symlinks are not permitted in confined paths")
    resolved = current.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise Forbidden("path escapes its configured root") from exc
    return resolved


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class TokenSigner:
    """HMAC signer backed by a local random secret with restrictive permissions.

    When a ``StateStore`` is provided, issued tokens register a one-time nonce
    that :meth:`verify` atomically consumes, so a replayed or forged nonce is
    rejected even with a valid signature. Product paths always pass the store;
    the degenerate no-store mode exists only for isolated CLI/tests.
    """

    IAT_SKEW_SECONDS = 300

    def __init__(self, state_root: Path, state: Any | None = None):
        self.secret_path = state_root / "token-secret"
        if not self.secret_path.exists():
            atomic_write(self.secret_path, secrets.token_bytes(32), mode=0o600)
        mode = self.secret_path.stat().st_mode & 0o777
        if mode != 0o600:
            os.chmod(self.secret_path, 0o600)
        self._secret = self.secret_path.read_bytes()
        if len(self._secret) < 32:
            raise InvalidRequest("token secret is invalid")
        self._state = state

    def issue(self, kind: str, claims: dict[str, Any], ttl_seconds: int = 900) -> str:
        now = int(time.time())
        for _ in range(3):
            payload = {
                "v": 1,
                "kind": kind,
                "iat": now,
                "exp": now + ttl_seconds,
                "nonce": secrets.token_hex(16),
                "claims": claims,
            }
            if self._state is not None:
                try:
                    self._state.issue_nonce(payload["nonce"])
                except Conflict:
                    continue  # nonce collision: regenerate
            encoded = b64url_encode(canonical_json(payload).encode("utf-8"))
            signature = b64url_encode(
                hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
            )
            return f"{encoded}.{signature}"
        raise InvalidRequest("could not register a fresh token nonce")

    def verify(self, token: str, kind: str, *, consume_nonce: bool = True) -> dict[str, Any]:
        """Verify signature, claims, and (optionally) single-use nonce.

        Approve paths pass ``consume_nonce=False`` because the same token is
        legitimately re-verified by the authorization landing point
        (apply/start), which consumes the nonce together with the approval.
        """
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = b64url_encode(
                hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(expected, supplied_signature):
                raise Forbidden("token signature is invalid")
            payload = json.loads(b64url_decode(encoded))
            if not isinstance(payload, dict):
                raise Forbidden("token is malformed")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Forbidden("token is malformed") from exc
        if payload.get("v") != 1 or payload.get("kind") != kind:
            raise Forbidden("token kind is invalid")
        now = int(time.time())
        exp = payload.get("exp")
        if not isinstance(exp, int) or exp <= now:
            raise Forbidden("token has expired")
        iat = payload.get("iat")
        if not isinstance(iat, int) or abs(now - iat) > self.IAT_SKEW_SECONDS:
            raise Forbidden("token timestamp is invalid")
        claims = payload.get("claims")
        if not isinstance(claims, dict):
            raise Forbidden("token claims are invalid")
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise Forbidden("token nonce is invalid")
        if consume_nonce and self._state is not None and not self._state.consume_nonce(nonce):
            raise Forbidden("token nonce was already used or is unknown")
        return claims

    def consume(self, token: str) -> None:
        """Atomically consume a token's nonce at the authorization commit point.

        Called only after every other check passed and the approval was
        consumed, so failed attempts never burn the capability.
        """
        try:
            encoded, _ = token.split(".", 1)
            payload = json.loads(b64url_decode(encoded))
            if not isinstance(payload, dict):
                raise Forbidden("token is malformed")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Forbidden("token is malformed") from exc
        nonce = payload.get("nonce")
        if (
            not isinstance(nonce, str)
            or not nonce
            or self._state is None
            or not self._state.consume_nonce(nonce)
        ):
            raise Forbidden("token nonce was already used or is unknown")
