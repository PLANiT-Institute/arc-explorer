"""Dump DATA_EXCHANGE_LAYER structure to the local JSON cache.

Run after Arc changes the warehouse, so the GUI can populate its table and
column pickers without hardcoding any part of the schema.

Equivalent to `./arc.command --refresh-schema`; kept as a standalone script for
use from an already-activated environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "gui"))

from arc_explorer.config import get_settings
from arc_explorer.connection import arc_connection
from arc_explorer.schema_cache import (
    fetch_schema,
    summarise_cache,
    write_schema_cache,
)


def main() -> None:
    """Introspect the configured schema and write the cache."""
    settings = get_settings()
    print(
        f"Connecting as {settings.user} (a browser window will open for SSO)...",
        flush=True,
    )

    with arc_connection(settings) as conn:
        payload = fetch_schema(conn, settings)

    path = write_schema_cache(payload, settings.schema_cache_path)
    print(summarise_cache(payload))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
