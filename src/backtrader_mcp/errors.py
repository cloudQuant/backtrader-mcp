"""Stable product errors exposed by the service and MCP boundary."""

from __future__ import annotations

import functools
import re
from typing import Any, Callable, TypeVar

# Absolute filesystem paths leaked into an error message (e.g. from a candidate
# traceback) are redacted before the message crosses the MCP boundary. The
# lookbehind avoids matching relative paths such as ``backtrader/__init__.py``
# and path-like fragments of URLs such as ``https://github.com/...``.
_ABS_UNIX_PATH = re.compile(r"(?<![\w/:])/(?:[\w.\-]+/)*[\w.\-]+")
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

    def __init__(self, message: str, suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion

    def as_client_text(self) -> str:
        """Structured, path-sanitized text for the MCP tool boundary."""
        text = f"[{self.code}] {sanitize_for_client(self.message)}"
        if self.suggestion:
            text += f"\nSuggestion: {self.suggestion}"
        return text

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": sanitize_for_client(self.message)}
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


class ClientToolError(Exception):
    """Exception whose text is already the client-facing structured message."""

    def __init__(self, text: str):
        super().__init__(text)
        self.text = text

    def __str__(self) -> str:
        return self.text


_F = TypeVar("_F", bound=Callable[..., Any])


def client_safe(fn: _F) -> _F:
    """Wrap a tool handler so failures cross the MCP boundary as structured,
    path-sanitized error text.

    The MCP SDK converts tool exceptions into ``CallToolResult(isError=True)``
    with the exception's ``str()``; this wrapper controls exactly that text.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ProductError as exc:
            raise ClientToolError(exc.as_client_text()) from exc
        except Exception as exc:
            raise ClientToolError(sanitize_for_client(str(exc))) from exc

    return wrapper  # type: ignore[return-value]


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
