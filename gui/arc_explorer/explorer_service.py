"""Catalogue-driven browsing and persistent, user-scoped data snapshots."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arc_explorer.sql_guard import guard


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class Explorer:
    """Build parameterized SQL only from catalogue-approved identifiers."""

    def __init__(self, conn, settings, catalogue: dict, storage: Path | None = None):
        self.conn, self.settings = conn, settings
        self.tables = {}
        for raw in catalogue["tables"]:
            item = {k.lower(): v for k, v in raw.items()}
            name = item["table_name"]
            self.tables[name] = {"name": name, "description": item.get("comment") or "",
                "row_count": item.get("row_count"), "columns": []}
        for raw in catalogue["columns"]:
            item = {k.lower(): v for k, v in raw.items()}
            if item["table_name"] in self.tables:
                self.tables[item["table_name"]]["columns"].append({"name": item["column_name"],
                    "type": item["data_type"], "description": item.get("comment") or ""})
        identity = json.dumps([settings.account, settings.user, settings.role, settings.database, settings.schema])
        scope = hashlib.sha256(identity.encode()).hexdigest()[:24]
        root = storage or settings.schema_cache_path.parent / "saved"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(root / f"{scope}.sqlite3")
        (root / f"{scope}.sqlite3").chmod(0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def catalogue(self) -> dict:
        return {"database": self.settings.database, "schema": self.settings.schema,
            "tables": list(self.tables.values()), "max_rows": self.settings.max_rows}

    def query(self, spec: dict, *, save: bool = False) -> dict:
        name = spec.get("table")
        if not isinstance(name, str) or name not in self.tables:
            raise ValueError("테이블을 선택하세요.")
        known = [c["name"] for c in self.tables[name]["columns"]]
        columns = spec.get("columns") or known
        if not isinstance(columns, list) or not columns or any(c not in known for c in columns):
            raise ValueError("올바른 열을 선택하세요.")
        columns = list(dict.fromkeys(columns))
        params, conditions = [], []
        search = str(spec.get("search", "")).strip()
        if search:
            conditions.append("(" + " OR ".join(f"TO_VARCHAR({quote(c)}) ILIKE %s" for c in columns) + ")")
            params.extend(["%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"] * len(columns))
        filters = spec.get("filters", [])
        if not isinstance(filters, list) or len(filters) > 20:
            raise ValueError("필터는 최대 20개까지 사용할 수 있습니다.")
        for f in filters:
            col, op = f.get("column"), f.get("operator")
            if col not in known:
                raise ValueError("알 수 없는 필터 열입니다.")
            field = quote(col)
            if op in ("is_null", "not_null"):
                conditions.append(field + (" IS NULL" if op == "is_null" else " IS NOT NULL"))
            elif op == "contains":
                conditions.append(f"TO_VARCHAR({field}) ILIKE %s")
                value = str(f.get("value", "")).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                params.append("%" + value + "%")
            elif op in ("=", "!=", ">", ">=", "<", "<="):
                conditions.append(f"{field} {op} %s")
                params.append(f.get("value", ""))
            else:
                raise ValueError("지원하지 않는 필터입니다.")
        limit = self.settings.max_rows if save else min(200, max(1, int(spec.get("limit", 100))))
        offset = 0 if save else max(0, min(1000000, int(spec.get("offset", 0))))
        source = ".".join(quote(v) for v in (self.settings.database, self.settings.schema, name))
        sql = f"SELECT {', '.join(quote(c) for c in columns)} FROM {source}"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sort = spec.get("sort") or columns[0]
        if sort not in known:
            raise ValueError("알 수 없는 정렬 열입니다.")
        direction = "DESC" if spec.get("direction") == "DESC" else "ASC"
        sql += f" ORDER BY {quote(sort)} {direction} LIMIT {limit + 1} OFFSET {offset}"
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchmany(limit + 1)
        result = {"table": name, "columns": columns, "rows": rows[:limit], "has_more": len(rows) > limit,
            "offset": offset, "limit": limit, "sql": sql, "parameters": params, "spec": spec}
        if save:
            result.update(id=uuid.uuid4().hex, name=str(spec.get("name") or name)[:160],
                saved_at=datetime.now(UTC).isoformat())
            self.db.execute("INSERT INTO datasets VALUES (?, ?)", (result["id"], json.dumps(result, default=str)))
            self.db.commit()
        return result

    def saved(self, identifier: str | None = None) -> Any:
        if identifier:
            row = self.db.execute("SELECT payload FROM datasets WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise ValueError("저장한 데이터를 찾을 수 없습니다.")
            return json.loads(row[0])
        items = [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM datasets ORDER BY rowid DESC")]
        return [{"id": r["id"], "name": r["name"], "table": r["table"], "saved_at": r["saved_at"],
            "row_count": len(r["rows"]), "has_more": r["has_more"]} for r in items]

    def run_sql(self, sql: str, limit: int = 100, save: bool = False, name: str = "") -> dict:
        """Execute a user-written read-only statement and return its rows.

        The statement is validated by `sql_guard.guard` before it reaches
        Snowflake: single statement, leading SELECT or WITH, no DML/DDL, and a
        row limit injected when the caller supplied none. Columns come from the
        cursor description because a free-form statement can return anything.

        Args:
            sql: Statement text as written by the user.
            limit: Row limit injected when the statement has no LIMIT of its own.
            save: Also store the result as a GUI dataset snapshot.
            name: Snapshot name; defaults to the leading line of the statement.

        Returns:
            Rows, column names, the guarded SQL actually executed, and execution
            metadata (`query_id`, `has_more`, `executed_at`).

        Raises:
            SqlNotAllowed: The statement failed read-only validation.
        """
        guarded = guard(sql, default_limit=max(1, int(limit)), max_rows=self.settings.max_rows)
        ceiling = self.settings.max_rows
        with self.conn.cursor() as cursor:
            cursor.execute(guarded.sql)
            rows = cursor.fetchmany(ceiling + 1)
            columns = [c[0] for c in (cursor.description or [])]
            query_id = getattr(cursor, "sfqid", None)
        result = {"table": "(sql)", "columns": columns, "rows": rows[:ceiling],
            "row_count": min(len(rows), ceiling), "has_more": len(rows) > ceiling,
            "sql": guarded.sql, "parameters": [], "executed": True, "query_id": query_id,
            "executed_at": datetime.now(UTC).isoformat(),
            "limit_applied": guarded.limit_applied, "had_own_limit": guarded.had_own_limit,
            "spec": {"_kind": "sql", "sql": sql, "limit": limit},
            "note": "Free-form read-only SQL. Columns and grain are whatever the statement returns; "
                    "no catalogue validation or join-path checking was applied."}
        if save:
            self.persist(result, name or sql.strip().splitlines()[0])
        return result

    def persist(self, result: dict, name: str) -> None:
        """Save an executed linked result using the existing dataset tabs."""
        result.update(id=uuid.uuid4().hex, name=name[:160], saved_at=datetime.now(UTC).isoformat())
        self.db.execute("INSERT INTO datasets VALUES (?, ?)", (result['id'], json.dumps(result, default=str)))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
