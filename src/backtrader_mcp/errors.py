"""Stable product errors exposed by the service and MCP boundary."""

from __future__ import annotations

import re

# Absolute filesystem paths leaked into an error message (e.g. from a candidate
# traceback) are redacted before the message crosses the MCP boundary. The
# lookbehind avoids matching relative paths such as ``backtrader/__init__.py``.
_ABS_UNIX_PATH = re.compile(r"(?<![\w/])/(?:[\w.\-]+/)*[\w.\-]+")
_ABS_WIN_PATH = re.compile(r"\b[A-Za-z]:\\(?:[\w.\-]+\\)*[\w.\-]+")


def sanitize_for_client(message: str) -> str:
    """Redact absolute paths from a client-facing error message.

    Conservative: only filesystem paths are redacted. Normal messages without
    absolute paths are returned unchanged, so stable error contracts hold.
    """
    if not isinstance(message, str):
        message = str(message)
    message = _ABS_UNIX_PATH.sub("<path>", message)
    message = _ABS_WIN_PATH.sub("<path>", message)
    return message


class ProductError(RuntimeError):
    """Base error with a stable machine-readable code."""

    code = "product_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": sanitize_for_client(self.message)}


class InvalidRequest(ProductError):
    code = "invalid_request"


class NotFound(ProductError):
    code = "not_found"


class Conflict(ProductError):
    code = "conflict"


class Forbidden(ProductError):
    code = "forbidden"


class StaleState(ProductError):
    code = "stale_state"


class ApprovalRequired(ProductError):
    code = "approval_required"
