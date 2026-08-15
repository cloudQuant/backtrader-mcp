"""Durable SQLite registry used by every product service."""

from __future__ import annotations

import builtins
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from .errors import Conflict, NotFound
from .util import canonical_json, sha256_json, utc_now


class StateStore:
    def __init__(self, state_root: Path):
        self.path = state_root / "state.sqlite3"
        # One connection per thread, held for the store's lifetime. Each
        # operation previously opened (and leaked) a fresh connection; caching
        # removes both the handle leak and the ResourceWarning flood while the
        # per-operation BEGIN IMMEDIATE/busy_timeout semantics stay unchanged.
        self._local = threading.local()
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            self._local.connection = connection
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    subject_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    subject_id TEXT,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nonces (
                    nonce TEXT PRIMARY KEY,
                    used_at TEXT
                );
                """)

    def put(
        self, kind: str, object_id: str, payload: dict[str, Any], *, replace: bool = False
    ) -> None:
        now = utc_now()
        sql = (
            "INSERT OR REPLACE INTO objects(kind,id,payload_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?)"
            if replace
            else "INSERT INTO objects(kind,id,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)"
        )
        try:
            with self.connect() as connection:
                connection.execute(sql, (kind, object_id, canonical_json(payload), now, now))
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"{kind} already exists: {object_id}") from exc

    def get(self, kind: str, object_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM objects WHERE kind=? AND id=?", (kind, object_id)
            ).fetchone()
        if row is None:
            raise NotFound(f"{kind} not found: {object_id}")
        return json.loads(row["payload_json"])

    def maybe_get(self, kind: str, object_id: str) -> dict[str, Any] | None:
        try:
            return self.get(kind, object_id)
        except NotFound:
            return None

    def list(self, kind: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM objects WHERE kind=? ORDER BY created_at,id", (kind,)
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_approvals(self) -> builtins.list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT approval_id, subject_type, subject_id, created_at, expires_at, used_at "
                "FROM approvals ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_audit(self, limit: int = 100) -> builtins.list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT seq, at, event, subject_id, details_json FROM audit "
                "ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "seq": row["seq"],
                "at": row["at"],
                "event": row["event"],
                "subject_id": row["subject_id"],
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    def clean_audit(self, before_iso: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM audit WHERE at < ?", (before_iso,))
            return cursor.rowcount

    def clean_idempotency(self, before_iso: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM idempotency WHERE created_at < ?", (before_iso,)
            )
            return cursor.rowcount

    def update(
        self,
        kind: str,
        object_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        expected: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """Read-modify-write one object inside a transaction.

        ``expected`` is an optional precondition evaluated against the
        transaction's fresh read. A failing precondition rolls back and raises
        ``Conflict`` so callers can implement compare-and-swap transitions.
        """
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM objects WHERE kind=? AND id=?", (kind, object_id)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise NotFound(f"{kind} not found: {object_id}")
            current = json.loads(row["payload_json"])
            if expected is not None and not expected(current):
                connection.rollback()
                raise Conflict(f"{kind} precondition failed: {object_id}")
            new_payload = mutator(current)
            connection.execute(
                "UPDATE objects SET payload_json=?,updated_at=? WHERE kind=? AND id=?",
                (canonical_json(new_payload), utc_now(), kind, object_id),
            )
            connection.commit()
        return new_payload

    def delete(self, kind: str, object_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, object_id))

    def checkpoint(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def replace_kind(self, kind: str, rows: builtins.list[dict[str, Any]]) -> int:
        """Replace every object of one kind in a single transaction.

        Used by catalog refresh: the whole kind is swapped atomically so
        concurrent readers observe either the old or the new snapshot, and
        entries whose source files disappeared stop appearing.
        """
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM objects WHERE kind=?", (kind,))
            connection.executemany(
                "INSERT INTO objects(kind,id,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                [(kind, row["id"], canonical_json(row), now, now) for row in rows],
            )
            connection.commit()
        return len(rows)

    def put_many(self, kind: str, rows: builtins.list[dict[str, Any]]) -> int:
        """Upsert many rows of one kind in a single transaction."""
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "INSERT OR REPLACE INTO objects(kind,id,payload_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?)",
                [(kind, row["id"], canonical_json(row), now, now) for row in rows],
            )
            connection.commit()
        return len(rows)

    def delete_many(self, kind: str, object_ids: builtins.list[str]) -> int:
        """Delete many rows of one kind in a single transaction."""
        if not object_ids:
            return 0
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "DELETE FROM objects WHERE kind=? AND id=?", [(kind, item) for item in object_ids]
            )
            connection.commit()
        return len(object_ids)

    def replace_prefix(self, kind: str, prefix: str, rows: builtins.list[dict[str, Any]]) -> int:
        """Atomically replace all rows of one kind whose id starts with ``prefix:``."""
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM objects WHERE kind=? AND id LIKE ?", (kind, f"{prefix}:%")
            )
            connection.executemany(
                "INSERT INTO objects(kind,id,payload_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                [(kind, row["id"], canonical_json(row), now, now) for row in rows],
            )
            connection.commit()
        return len(rows)

    def clean_approvals(self, before_iso: str) -> int:
        """Delete approvals that were consumed or expired before a timestamp."""
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM approvals WHERE used_at < ? OR expires_at < ?",
                (before_iso, before_iso),
            )
            return cursor.rowcount

    def issue_nonce(self, nonce: str) -> None:
        """Register a freshly generated token nonce (collision-safe insert)."""
        try:
            with self.connect() as connection:
                connection.execute("INSERT INTO nonces(nonce,used_at) VALUES(?,NULL)", (nonce,))
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"nonce already exists: {nonce}") from exc

    def consume_nonce(self, nonce: str) -> bool:
        """Atomically consume one nonce; False when absent or already used."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT used_at FROM nonces WHERE nonce=?", (nonce,)
            ).fetchone()
            if row is None or row["used_at"] is not None:
                connection.rollback()
                return False
            connection.execute("UPDATE nonces SET used_at=? WHERE nonce=?", (utc_now(), nonce))
            connection.commit()
        return True

    def idempotent_get(
        self, scope: str, key: str, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        request_hash = sha256_json(request)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT request_hash,response_json FROM idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise Conflict("idempotency key was already used with a different request")
        return json.loads(row["response_json"])

    def idempotent_put(
        self, scope: str, key: str, request: dict[str, Any], response: dict[str, Any]
    ) -> None:
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO idempotency(scope,key,request_hash,response_json,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (scope, key, sha256_json(request), canonical_json(response), utc_now()),
                )
        except sqlite3.IntegrityError:
            prior = self.idempotent_get(scope, key, request)
            if prior != response:
                raise Conflict("concurrent idempotency response differs")

    def create_approval(
        self, subject_type: str, subject_id: str, subject_hash: str, expires_at: str
    ) -> dict[str, Any]:
        approval_id = f"approval_{uuid.uuid4().hex}"
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO approvals VALUES(?,?,?,?,?,?,NULL)",
                (approval_id, subject_type, subject_id, subject_hash, created_at, expires_at),
            )
        result = {
            "approval_id": approval_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_hash": subject_hash,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        self.audit("approval.created", subject_id, result)
        return result

    def consume_approval(
        self, approval_id: str, subject_type: str, subject_id: str, subject_hash: str
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
            if (
                row is None
                or row["subject_type"] != subject_type
                or row["subject_id"] != subject_id
                or row["subject_hash"] != subject_hash
                or row["used_at"] is not None
                or row["expires_at"] <= now
            ):
                connection.rollback()
                raise Conflict("approval is missing, expired, used, or bound to different content")
            connection.execute(
                "UPDATE approvals SET used_at=? WHERE approval_id=?", (now, approval_id)
            )
            connection.commit()
        self.audit("approval.consumed", subject_id, {"approval_id": approval_id})

    def audit(self, event: str, subject_id: str | None, details: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit(at,event,subject_id,details_json) VALUES(?,?,?,?)",
                (utc_now(), event, subject_id, canonical_json(details)),
            )
