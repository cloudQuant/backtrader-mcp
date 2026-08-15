from __future__ import annotations

import pytest

from backtrader_mcp.errors import (
    ClientToolError,
    InvalidRequest,
    ProductError,
    client_safe,
    sanitize_for_client,
)


def test_product_error_client_text_has_code_and_sanitizes_paths():
    error = InvalidRequest(
        "dataset file /abs/path/prices.csv failed column mapping",
        suggestion="map datetime/open/high/low/close/volume columns explicitly",
    )
    text = error.as_client_text()
    assert text == (
        "[invalid_request] dataset file <path> failed column mapping\n"
        "Suggestion: map datetime/open/high/low/close/volume columns explicitly"
    )
    assert "/abs/path" not in text


def test_product_error_client_text_without_suggestion():
    assert ProductError("plain message").as_client_text() == "[product_error] plain message"


def test_product_error_as_dict_includes_suggestion():
    error = InvalidRequest("bad input", suggestion="try again")
    assert error.as_dict() == {
        "code": "invalid_request",
        "message": "bad input",
        "suggestion": "try again",
    }


def test_product_error_as_dict_without_suggestion_keeps_shape():
    assert ProductError("plain").as_dict() == {
        "code": "product_error",
        "message": "plain",
    }


def test_client_safe_wraps_product_error_with_structured_text():
    @client_safe
    def failing_tool() -> None:
        raise InvalidRequest("limit 0 rejected", suggestion="use a limit between 1 and 100")

    with pytest.raises(ClientToolError) as caught:
        failing_tool()
    assert (
        str(caught.value)
        == "[invalid_request] limit 0 rejected\nSuggestion: use a limit between 1 and 100"
    )


def test_client_safe_sanitizes_generic_exceptions():
    @client_safe
    def broken_tool() -> None:
        raise ValueError("cannot open /Users/someone/secret/data.csv")

    with pytest.raises(ClientToolError) as caught:
        broken_tool()
    text = str(caught.value)
    assert "cannot open" in text
    assert "/Users/someone" not in text
    assert "<path>" in text


def test_client_safe_preserves_returns():
    @client_safe
    def ok_tool(value: int) -> int:
        return value * 2

    assert ok_tool(21) == 42


def test_sanitize_for_client_keeps_relative_paths():
    message = "strategy file strategies/run.py failed at line 12"
    assert sanitize_for_client(message) == message


def test_sanitize_for_client_preserves_urls():
    message = "failed to fetch https://github.com/cloudquant/backtrader/archive.zip"
    assert sanitize_for_client(message) == message
