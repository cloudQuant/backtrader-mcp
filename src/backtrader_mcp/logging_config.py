"""Structured logging configured from the environment.

Logs go to stderr so the stdio MCP protocol frames on stdout are never
contaminated. The level is read from ``BACKTRADER_MCP_LOG_LEVEL`` (default
``WARNING``). Call :func:`configure_logging` once at process entry (the CLI
serve command and the worker entrypoint both do this); other modules obtain
the configured logger via ``logging.getLogger("backtrader_mcp")``.
"""

from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "backtrader_mcp"
_CONFIGURED = False


def configure_logging() -> logging.Logger:
    """Install the stderr handler on the product logger and return it."""
    global _CONFIGURED
    level_name = os.environ.get("BACKTRADER_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logger = logging.getLogger(_LOGGER_NAME)
    if not _CONFIGURED:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                "%Y-%m-%dT%H:%M:%SZ",
            )
        )
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED = True
    logger.setLevel(level)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the product logger namespace."""
    base = _LOGGER_NAME if not name else f"{_LOGGER_NAME}.{name}"
    return logging.getLogger(base)
