"""Centralised logging for Arc Explorer.

Logs shapes, row counts and query ids -- never full result sets, and never the
contents of a row (the warehouse holds licensed third-party data).
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger writing to stderr at the configured level."""
    global _CONFIGURED

    if not _CONFIGURED:
        from arc_explorer.config import log_level

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root = logging.getLogger("arc_explorer")
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(log_level())
        root.propagate = False
        _CONFIGURED = True

    return logging.getLogger(f"arc_explorer.{name}")
