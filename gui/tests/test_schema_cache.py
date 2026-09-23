"""Tests for the schema cache, driven by a stub cursor instead of a warehouse.

The live introspection is exercised by `arc.command --refresh-schema`; what is
pinned here is the payload shape the GUI reads and the fact that only
structure, never data rows, is written to disk.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from arc_explorer.schema_cache import (
    COLUMNS_SQL,
    TABLES_SQL,
    fetch_schema,
    write_schema_cache,
)
from test_connection import make_settings

TABLES = pd.DataFrame(
    [
        {"TABLE_NAME": "COMPANY", "TABLE_TYPE": "BASE TABLE", "ROW_COUNT": 12},
        {"TABLE_NAME": "METRIC", "TABLE_TYPE": "BASE TABLE", "ROW_COUNT": 34},
    ]
)
COLUMNS = pd.DataFrame(
    [
        {"TABLE_NAME": "COMPANY", "COLUMN_NAME": "COMPANY_ID", "DATA_TYPE": "NUMBER"},
        {"TABLE_NAME": "COMPANY", "COLUMN_NAME": "NAME", "DATA_TYPE": "TEXT"},
        {"TABLE_NAME": "METRIC", "COLUMN_NAME": "METRIC_ID", "DATA_TYPE": "NUMBER"},
    ]
)


class StubCursor:
    def __init__(self, recorder: list[str]):
        self._recorder = recorder
        self._sql = ""
        self.sfqid = "stub-query-id"

    def execute(self, sql, params=None):
        self._sql = sql
        self._recorder.append(sql)

    def fetch_pandas_all(self):
        return (
            TABLES.copy()
            if "information_schema.tables" in self._sql
            else COLUMNS.copy()
        )

    def close(self):
        pass


class StubConnection:
    def __init__(self):
        self.statements: list[str] = []

    def cursor(self):
        return StubCursor(self.statements)


@pytest.fixture
def payload():
    return fetch_schema(StubConnection(), make_settings())


def test_payload_records_the_scope_it_was_read_from(payload):
    assert payload["database"] == "ARCDW_PROD"
    assert payload["schema"] == "DATA_EXCHANGE_LAYER"


def test_payload_carries_tables_and_columns(payload):
    assert [t["TABLE_NAME"] for t in payload["tables"]] == ["COMPANY", "METRIC"]
    assert len(payload["columns"]) == 3


def test_both_queries_are_scoped_to_the_configured_schema():
    conn = StubConnection()
    fetch_schema(conn, make_settings(database="OTHER_DB", schema="OTHER_SCHEMA"))
    assert len(conn.statements) == 2
    for sql in conn.statements:
        assert "OTHER_DB.information_schema" in sql
        assert "'OTHER_SCHEMA'" in sql


def test_queries_read_structure_only():
    # A regression guard: the cache must never pull licensed data rows.
    for sql in (TABLES_SQL, COLUMNS_SQL):
        assert "information_schema" in sql
        assert "SELECT *" not in sql


def test_cache_round_trips_through_disk(tmp_path, payload):
    path = write_schema_cache(payload, tmp_path / "nested" / "schema_cache.json")
    assert path.exists()
    assert json.loads(path.read_text()) == payload
