"""Catalogue-backed joins shared by the browser and MCP. No raw SQL input."""
from __future__ import annotations

import heapq
from datetime import UTC, datetime
from typing import Any

from arc_explorer.explorer_service import quote


def literal(value: Any) -> str:
    """Render a parameter for the inspectable SQL copy, never for execution."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


class LinkedQuery:
    """Resolve joins through identifier keys and execute parameterized SELECTs."""

    def __init__(self, explorer):
        self.explorer = explorer
        self.settings = explorer.settings
        self.tables = explorer.tables
        self.edges: list[dict] = []
        # Explicit semantic links checked against the current catalogue.
        for left, lc, right, rc in [
            ("COMPANY", "COMPANY_ID", "COMPANY_SECTOR", "COMPANY_ID"),
            ("COMPANY_SECTOR", "SECTOR_ID", "SECTOR", "SECTOR_ID"),
            ("COMPANY", "HQ_COUNTRY_CODE_ALPHA2", "DEX_COUNTRY", "COUNTRY_CODE_ALPHA2"),
        ]:
            self._edge(left, lc, right, rc, "semantic_mapping", 1)
        for parent in self.tables:
            key = parent + "_ID"
            if key not in self.columns(parent):
                continue
            for child in self.tables:
                if child != parent and key in self.columns(child):
                    self._edge(parent, key, child, key, "catalogue_key_convention", 10)

    def columns(self, table: str) -> list[str]:
        if table not in self.tables:
            raise ValueError(f"Unknown table: {table}")
        return [c["name"] for c in self.tables[table]["columns"]]

    def _edge(self, left, lc, right, rc, source, cost):
        if left not in self.tables or right not in self.tables:
            return
        if lc not in self.columns(left) or rc not in self.columns(right):
            return
        if any({(e['left'], e['left_column']), (e['right'], e['right_column'])} == {(left, lc), (right, rc)} for e in self.edges):
            return
        self.edges.append({"left": left, "left_column": lc, "right": right, "right_column": rc,
            "source": source, "cost": cost, "constraint_verified": False})

    def path(self, start: str, target: str) -> list[dict]:
        self.columns(start)
        self.columns(target)
        queue: list[tuple[int, int, str, list[dict]]] = [(0, 0, start, [])]
        visited: set[str] = set()
        serial = 0
        while queue:
            cost, _, table, path = heapq.heappop(queue)
            if table == target:
                return path
            if table in visited:
                continue
            visited.add(table)
            if len(path) >= 4:
                continue
            for edge in self.edges:
                if table not in (edge['left'], edge['right']):
                    continue
                other = edge['right'] if table == edge['left'] else edge['left']
                if other in visited:
                    continue
                oriented = dict(edge)
                if table == edge['right']:
                    oriented.update(left=table, left_column=edge['right_column'], right=other, right_column=edge['left_column'])
                serial += 1
                heapq.heappush(queue, (cost + edge['cost'], serial, other, path + [oriented]))
        raise ValueError(f"No supported key path from {start} to {target}; a relationship mapping is required.")

    def relationships(self, base: str) -> dict:
        self.columns(base)
        reachable = []
        for target in self.tables:
            if target == base:
                continue
            try:
                reachable.append({"table": target, "path": self.path(base, target)})
            except ValueError:
                pass
        return {"base_table": base, "reachable": reachable,
            "note": "Identifier-based mappings, not warehouse-verified foreign keys. Inspect the path and grain; no joins on company names."}

    def _source(self, table: str) -> str:
        self.columns(table)
        return '.'.join(quote(v) for v in (self.settings.database, self.settings.schema, table))

    def compile(self, spec: dict, *, save: bool = False) -> dict:
        base = spec.get('base_table') or spec.get('table')
        if not isinstance(base, str):
            raise ValueError('A base table is required.')  # noqa: TRY004 - missing input, surfaced to the caller
        known = self.columns(base)
        fields = spec.get('columns') or [{'table': base, 'column': c} for c in known]
        filters = spec.get('filters') or []
        aggregates = spec.get('aggregates') or []
        if len(fields) > 100 or len(filters) > 20 or len(aggregates) > 10:
            raise ValueError('Too many selected columns, filters or aggregates.')
        aliases = {base: 't0'}
        joins, used_edges = [], []

        def ref(field):
            table, column = field.get('table', base), field.get('column')
            if column not in self.columns(table):
                raise ValueError(f'Unknown column: {table}.{column}')
            if table not in aliases:
                for edge in self.path(base, table):
                    right = edge['right']
                    if right in aliases:
                        continue
                    aliases[right] = f't{len(aliases)}'
                    joins.append(f"LEFT JOIN {self._source(right)} {aliases[right]} ON {aliases[edge['left']]}.{quote(edge['left_column'])} = {aliases[right]}.{quote(edge['right_column'])}")
                    used_edges.append(edge)
            return f'{aliases[table]}.{quote(column)}'

        expressions, labels = [], []
        for field in fields:
            label = f"{field.get('table', base)}.{field['column']}"
            if label in labels:
                continue
            expressions.append(ref(field) + ' AS ' + quote(label))
            labels.append(label)
        group_expressions = [ref(f) for f in fields]
        for aggregate in aggregates:
            func = str(aggregate.get('function', '')).upper()
            if func not in ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX'):
                raise ValueError('Unsupported aggregation.')
            expression = ref(aggregate)
            label = str(aggregate.get('alias') or f"{func}_{aggregate['column']}")
            if label in labels or len(label) > 100:
                raise ValueError('Aggregate alias must be unique and under 100 characters.')
            expressions.append(f'{func}({expression}) AS {quote(label)}')
            labels.append(label)
        params: list[Any] = []
        conditions: list[str] = []
        for f in filters:
            expression, operator = ref(f), f.get('operator', '=')
            value = f.get('value')
            if operator in ('is_null', 'not_null'):
                conditions.append(expression + (' IS NULL' if operator == 'is_null' else ' IS NOT NULL'))
            elif operator in ('contains', 'contains_any'):
                values = value if operator == 'contains_any' else [value]
                if not isinstance(values, list) or not 1 <= len(values) <= 30:
                    raise ValueError('Search terms must be a list of 1–30 values.')
                conditions.append('(' + ' OR '.join(f'TO_VARCHAR({expression}) ILIKE %s' for _ in values) + ')')
                params.extend('%' + str(v).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for v in values)
            elif operator in ('in', '=','!=','>','>=','<','<='):
                if operator == 'in':
                    if not isinstance(value, list) or not 1 <= len(value) <= 100:
                        raise ValueError('IN needs 1–100 values.')
                    conditions.append(expression + ' IN (' + ', '.join(['%s'] * len(value)) + ')')
                    params.extend(value)
                else:
                    if isinstance(value, (dict, list)):
                        raise ValueError('Comparison value must be a scalar.')
                    conditions.append(expression + ' ' + operator + ' %s')
                    params.append(value)
            else:
                raise ValueError(f'Unsupported filter: {operator}')
        search = str(spec.get('search') or '').strip()
        if search:
            conditions.append('(' + ' OR '.join(f'TO_VARCHAR({ref(f)}) ILIKE %s' for f in fields) + ')')
            params.extend(['%' + search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'] * len(fields))
        # Joining multiple one-to-many branches can multiply sums. Do not
        # pretend DISTINCT fixes it; require users to aggregate separately.
        if aggregates and len(used_edges) > 1:
            raise ValueError('Aggregate one relationship at a time to avoid multiplying fact rows. Query each measure separately.')
        order = spec.get('sort') or labels[0]
        if isinstance(order, dict):
            order = f"{order.get('table', base)}.{order.get('column')}"
        if order not in labels:
            raise ValueError('Sort must refer to a selected output column.')
        limit = self.settings.max_rows if save else max(1, min(int(spec.get('limit',100)), self.settings.max_rows))
        offset = 0 if save else max(0, min(int(spec.get('offset',0)),1000000))
        sql = ('SELECT ' if aggregates else 'SELECT DISTINCT ') + ', '.join(expressions)
        sql += f' FROM {self._source(base)} t0'
        if joins:
            sql += '\n' + '\n'.join(joins)
        if conditions:
            sql += '\nWHERE ' + ' AND '.join(conditions)
        if aggregates:
            sql += '\nGROUP BY ' + ', '.join(group_expressions)
        direction = 'DESC' if spec.get('direction') == 'DESC' else 'ASC'
        sql += f'\nORDER BY {quote(order)} {direction}\nLIMIT {limit + 1} OFFSET {offset}'
        pieces = sql.split('%s')
        rendered = pieces[0] + ''.join(literal(p) + tail for p, tail in zip(params,pieces[1:]))
        return {"sql": sql, "parameters": params, "display_sql": rendered, "columns": labels, "limit": limit,
            "offset": offset, "relationships": used_edges, "base_table": base,
            "grain": 'Distinct combinations of selected fields. Multiple related rows can produce multiple rows per company.',
            "relationship_note": 'Key mappings are catalogue-based; uniqueness/foreign-key constraints are not asserted.'}

    def run(self, spec: dict, output: str = 'both', save: bool = False) -> dict:
        if output not in ('table','sql','both'):
            raise ValueError('output must be table, sql, or both')
        plan = self.compile(spec, save=save)
        if output == 'sql':
            if save:
                raise ValueError('Saving requires SQL execution.')
            return dict(plan, executed=False)
        with self.explorer.conn.cursor() as cursor:
            cursor.execute(plan['sql'], plan['parameters'])
            rows = cursor.fetchmany(plan['limit'] + 1)
            query_id = getattr(cursor, 'sfqid', None)
        result = dict(plan, rows=rows[:plan['limit']], row_count=min(len(rows),plan['limit']),
            has_more=len(rows)>plan['limit'], executed=True, query_id=query_id,
            executed_at=datetime.now(UTC).isoformat(), table=plan['base_table'],
            spec=dict(spec, _kind='linked'))
        if save:
            self.explorer.persist(result, str(spec.get('name') or plan['base_table']))
        return result

    def lookup(self, table: str, column: str, search: str = '', limit: int = 100) -> dict:
        filters = [{'table':table,'column':column,'operator':'contains','value':search}] if search else []
        return self.run({"base_table": table,"columns": [{"table": table,"column": column}],"filters": filters,"limit": limit})

    def companies(self, country_code: str = '', country_name: str = '', sector_terms: list[str] | None = None,
                  classification: str = '', limit: int = 100, output: str = 'both', save: bool = False) -> dict:
        fields = [{'table':'COMPANY','column':c} for c in ('COMPANY_ID','COMPANY_NAME','LEI','HQ_COUNTRY_NAME') if c in self.columns('COMPANY')]
        filters: list[dict[str, object]] = []
        if country_code:
            filters.append({"table": 'COMPANY',"column": 'HQ_COUNTRY_CODE_ALPHA2',"operator": '=',"value": country_code.upper()})
        if country_name:
            filters.append({"table": 'COMPANY',"column": 'HQ_COUNTRY_NAME',"operator": 'contains',"value": country_name})
        if sector_terms:
            filters.append({"table": 'COMPANY_SECTOR',"column": 'SECTOR_NAME',"operator": 'contains_any',"value": sector_terms})
        if classification:
            filters.append({"table": 'COMPANY_SECTOR',"column": 'SECTOR_CLASSIFICATION_NAME',"operator": '=',"value": classification})
        result = self.run({"base_table": 'COMPANY',"columns": fields,"filters": filters,"limit": limit},output,save)
        interpretation: dict[str, object] = {'country_basis': 'company headquarters, not operating markets',
            'sector_basis': 'COMPANY_SECTOR membership; supplied terms are ORed and are not a universal electricity taxonomy',
            'sector_terms': sector_terms or [], 'classification': classification or 'all classifications'}
        result['interpretation'] = interpretation
        return result
