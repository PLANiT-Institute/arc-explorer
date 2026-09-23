"""Tests for the read-only SQL guard.

The guard is the only thing between the raw-SQL tab and the warehouse, so the
injection-style cases matter more than the happy path.
"""

from __future__ import annotations

import pytest
from arc_explorer.sql_guard import SqlNotAllowed, guard, scrub

LIMITS = {"default_limit": 500, "max_rows": 5000}


def test_plain_select_gets_a_limit():
    result = guard("SELECT * FROM company", **LIMITS)
    assert result.sql.endswith("LIMIT 500")
    assert result.limit_applied == 500
    assert not result.had_own_limit


def test_cte_is_allowed():
    sql = "WITH latest AS (SELECT MAX(id) AS id FROM t) SELECT * FROM latest"
    assert guard(sql, **LIMITS).sql.endswith("LIMIT 500")


def test_own_limit_is_respected_and_not_doubled():
    result = guard("SELECT * FROM company LIMIT 10", **LIMITS)
    assert result.sql.count("LIMIT") == 1
    assert result.had_own_limit
    assert result.limit_applied is None


def test_trailing_semicolon_is_stripped_not_rejected():
    assert guard("SELECT 1;", **LIMITS).sql.startswith("SELECT 1")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM company",
        "DROP TABLE company",
        "UPDATE company SET x = 1",
        "CREATE TABLE t AS SELECT 1",
        "INSERT INTO t VALUES (1)",
        "TRUNCATE TABLE t",
        "GRANT SELECT ON t TO ROLE r",
        "CALL my_proc()",
        "USE ROLE accountadmin",
        "SET x = 1",
        "SHOW TABLES",
    ],
)
def test_non_read_statements_are_rejected(sql):
    with pytest.raises(SqlNotAllowed):
        guard(sql, **LIMITS)


def test_second_statement_is_rejected():
    with pytest.raises(SqlNotAllowed, match="one statement"):
        guard("SELECT 1; DROP TABLE company", **LIMITS)


def test_semicolon_hidden_in_a_comment_is_still_rejected():
    with pytest.raises(SqlNotAllowed, match="one statement"):
        guard("SELECT 1 /* ; DROP TABLE company */ ; DELETE FROM t", **LIMITS)


def test_dml_hidden_in_a_cte_is_rejected():
    with pytest.raises(SqlNotAllowed, match="read-only"):
        guard("WITH x AS (DELETE FROM company RETURNING 1) SELECT * FROM x", **LIMITS)


def test_forbidden_word_inside_a_string_literal_is_allowed():
    # A company legitimately named with a keyword must not trip the guard.
    result = guard(
        "SELECT * FROM company WHERE company_name ILIKE '%DROP TABLE%'", **LIMITS
    )
    assert result.sql.endswith("LIMIT 500")


def test_forbidden_word_inside_a_line_comment_is_allowed():
    result = guard("SELECT 1 -- todo: DELETE this later\n", **LIMITS)
    assert result.limit_applied == 500


def test_column_named_like_a_keyword_is_allowed():
    result = guard("SELECT update_date, created_at FROM t", **LIMITS)
    assert result.limit_applied == 500


def test_escaped_quote_does_not_unbalance_the_scrubber():
    result = guard("SELECT * FROM t WHERE name = 'O''Brien; DROP TABLE t'", **LIMITS)
    assert result.limit_applied == 500


def test_default_limit_is_capped_by_max_rows():
    result = guard("SELECT 1", default_limit=99_999, max_rows=100)
    assert result.limit_applied == 100


def test_empty_statement_is_rejected():
    with pytest.raises(SqlNotAllowed, match="empty"):
        guard("   ;  ", **LIMITS)


def test_comment_only_statement_is_rejected():
    with pytest.raises(SqlNotAllowed):
        guard("-- just a note", **LIMITS)


def test_scrub_preserves_offsets():
    sql = "SELECT 'abc' FROM t"
    scrubbed = scrub(sql)
    assert len(scrubbed) == len(sql)
    assert scrubbed.startswith("SELECT ")
    assert "abc" not in scrubbed
