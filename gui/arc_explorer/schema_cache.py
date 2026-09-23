"""Introspection of the Arc schema into a local JSON cache.

The GUI populates its table and column pickers from this cache rather than
hardcoding any part of the warehouse. Refresh it after Arc changes the schema.

The cache holds structure only -- table names, column names, types, row counts
-- never data rows, which are licensed third-party content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snowflake.connector import SnowflakeConnection

from arc_explorer.config import Settings
from arc_explorer.connection import fetch_dataframe
from arc_explorer.logger import get_logger

LOGGER = get_logger("schema_cache")

TABLES_SQL = """
SELECT table_name, table_type, row_count, bytes, comment
FROM {database}.information_schema.tables
WHERE table_schema = '{schema}'
ORDER BY table_name
"""

COLUMNS_SQL = """
SELECT table_name, column_name, ordinal_position, data_type,
       is_nullable, comment
FROM {database}.information_schema.columns
WHERE table_schema = '{schema}'
ORDER BY table_name, ordinal_position
"""


def fetch_schema(conn: SnowflakeConnection, settings: Settings) -> dict[str, Any]:
    """Read the table and column catalogue for the configured schema.

    Args:
        conn: An open connection.
        settings: Settings naming the database and schema to introspect.

    Returns:
        A JSON-serialisable payload with `database`, `schema`, `tables` and
        `columns` keys.
    """
    scope = {"database": settings.database, "schema": settings.schema}

    tables = fetch_dataframe(conn, TABLES_SQL.format(**scope))
    columns = fetch_dataframe(conn, COLUMNS_SQL.format(**scope))
    LOGGER.info(
        "Introspected %s: %d tables, %d columns",
        settings.qualified_schema,
        tables.shape[0],
        columns.shape[0],
    )

    return {
        "database": settings.database,
        "schema": settings.schema,
        "tables": json.loads(tables.to_json(orient="records")),
        "columns": json.loads(columns.to_json(orient="records")),
    }


def write_schema_cache(payload: dict[str, Any], path: Path) -> Path:
    """Write the introspected schema to disk, creating parent directories.

    Args:
        payload: Output of `fetch_schema`.
        path: Destination file, normally `Settings.schema_cache_path`.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    LOGGER.info("Wrote %s (%.0f KB)", path, path.stat().st_size / 1024)
    return path


def summarise_cache(payload: dict[str, Any]) -> str:
    """One line describing a cached schema, for console output.

    Args:
        payload: Output of `fetch_schema`, or a cache loaded from disk.

    Returns:
        A summary such as `ARCDW_PROD.DATA_EXCHANGE_LAYER: 42 tables, 517 columns`.
    """
    database = payload.get("database", "?")
    schema = payload.get("schema", "?")
    tables = len(payload.get("tables", []))
    columns = len(payload.get("columns", []))
    return f"{database}.{schema}: {tables} tables, {columns} columns"
