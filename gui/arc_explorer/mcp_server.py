"""Arc MCP stdio server. The host AI plans; shared Arc SQL code executes."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from arc_explorer.mcp_bridge import Bridge

INSTRUCTIONS = """Use Arc tools for warehouse answers. NEVER invent or return data values without a successful SQL tool execution in this request. Start with catalogue/relationships, then lookup actual country/sector labels, then query. Explain join paths, row grain, classification and truncation. output=sql returns ONLY an unexecuted plan, never data. Use the existing arc.command terminal login; never request passwords or MFA in chat.
Natural-language interpretation belongs to you, the MCP host AI. Translate user intent into typed query fields and filters; do not use a keyword-only text parser. For '일본의 전력 업체', use HQ country code JP (headquarters, not markets), inspect COMPANY_SECTOR.SECTOR_NAME and SECTOR_CLASSIFICATION_NAME through arc_lookup_values, choose or clarify electricity/power classifications, then arc_search_companies or arc_query. Relate tables using ID keys, never names. COMPANY -> COMPANY_SECTOR -> SECTOR is the preferred sector path. Country/sector labels vary across providers; disclose matching terms and classification. Read relationship metadata: convention-derived keys are not verified foreign-key constraints. Multiple fact joins can multiply rows; do not sum multiplied results. All data tools execute parameterized SQL and expose execution metadata. arc_sql runs a statement you write yourself, for questions the typed tools cannot express (window functions, UNION, self-joins, joins no key path covers); it is read-only and single-statement, it is NOT catalogue-validated, so fully qualify tables and state the grain and caveats yourself. Prefer arc_query whenever it fits. Local saved snapshots cannot be used as fresh facts; arc_refresh_saved reruns their SQL. Return a table and the executed SQL when requested. Use save=true to put the executed query into the same GUI's saved-data list.
"""


class Column(BaseModel):
    table: str
    column: str


class Filter(Column):
    operator: Literal['=','!=','>','>=','<','<=','contains','contains_any','in','is_null','not_null'] = '='
    value: Any = None


class Aggregate(Column):
    function: Literal['COUNT','SUM','AVG','MIN','MAX']
    alias: str | None = None


def create_server(session_path: Path) -> FastMCP:
    """Create a server without logging in or consuming stdio for credentials."""
    bridge = Bridge(session_path)
    server = FastMCP('Arc Data Explorer', instructions=INSTRUCTIONS)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=read)
    def arc_status() -> dict:
        """Check the live CLI-authenticated Arc session. No warehouse data values."""
        return bridge.call('status')

    @server.tool(annotations=read)
    def arc_catalogue(search: str = '') -> dict:
        """Find tables, columns and types in cached structure. This is not data evidence."""
        return bridge.call('catalogue', {'search':search})

    @server.tool(annotations=read)
    def arc_relationships(base_table: str = 'COMPANY') -> dict:
        """Show supported ID-key paths, including intermediate tables and mapping provenance."""
        return bridge.call('relationships', {'base_table':base_table})

    @server.tool(annotations=read)
    def arc_lookup_values(table: str, column: str, search: str = '', limit: int = 100) -> dict:
        """Execute DISTINCT SQL to discover actual countries, sectors or other dimension values."""
        return bridge.call('lookup', {'table': table,'column': column,'search': search,'limit': limit})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
    def arc_search_companies(country_code: str = '', country_name: str = '',
            sector_terms: list[str] = Field(default_factory=list), classification: str = '',
            limit: int = 100, output: Literal['table','sql','both'] = 'both', save: bool = False) -> dict:
        """Join companies to sector memberships. E.g. HQ=JP plus discovered electricity sector names.

        Country means headquarters. Terms are ORed; all other filters are ANDed.
        Distinct company output prevents one result per sector membership.
        save=true also creates a local GUI dataset. output=sql never executes or returns rows.
        """
        return bridge.call('companies', {'country_code': country_code,'country_name': country_name,
            'sector_terms': sector_terms,'classification': classification,'limit': limit,'output': output,'save': save})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
    def arc_query(base_table: str, columns: list[Column], filters: list[Filter] = Field(default_factory=list),
            aggregates: list[Aggregate] = Field(default_factory=list), search: str = '',
            sort: str = '', direction: Literal['ASC','DESC'] = 'ASC', limit: int = 100, offset: int = 0,
            output: Literal['table','sql','both'] = 'both', save: bool = False, name: str = '') -> dict:
        """Query fields and filters across connected tables; join paths are resolved and shown.

        columns are {table,column}; filters additionally have operator,value. Multiple filters
        are ANDed. 'in' and 'contains_any' accept lists. Default results are DISTINCT selected
        field combinations, not necessarily unique companies. sort is an output label TABLE.COLUMN
        or aggregate alias. With aggregates, columns become group keys; multi-edge aggregates
        are rejected to avoid ambiguous fanout. Save writes a local GUI snapshot. All returned
        data rows come from this execution, with SQL, parameters, query_id and has_more.
        """
        spec = {'base_table': base_table, 'columns': [c.model_dump() for c in columns],
            'filters': [f.model_dump() for f in filters], 'aggregates': [a.model_dump() for a in aggregates],
            'search': search,'sort': sort,'direction': direction,'limit': limit,'offset': offset,'name': name}
        return bridge.call('query', {'spec': spec,'output': output,'save': save})

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False))
    def arc_sql(sql: str, limit: int = 100, save: bool = False, name: str = '') -> dict:
        """Execute a read-only SQL statement written directly, for anything the typed tools cannot express.

        Use this when arc_query cannot express the question: window functions, UNION,
        multi-level CTEs, self-joins, or a join no key path covers. Prefer arc_query
        when it fits, because that path validates tables, columns and join grain.

        Only one statement, and it must start with SELECT or WITH. INSERT/UPDATE/DELETE/
        MERGE/CREATE/DROP/ALTER/TRUNCATE/GRANT/COPY/CALL are rejected before execution.
        A LIMIT is added when the statement has none; an existing LIMIT is kept.
        Fully qualify tables as DATABASE.SCHEMA.TABLE (see arc_status for the current pair).
        Returns the exact SQL executed, columns from the cursor, query_id and has_more.
        Nothing here is catalogue-checked, so state the grain and caveats yourself.
        """
        return bridge.call('sql', {'sql': sql, 'limit': limit, 'save': save, 'name': name})

    @server.tool(annotations=read)
    def arc_saved_datasets() -> dict:
        """List local snapshot names/IDs only; never return cached data values."""
        return bridge.call('saved')

    @server.tool(annotations=read)
    def arc_refresh_saved(dataset_id: str) -> dict:
        """Re-execute the saved dataset query and return current SQL results, not cached rows."""
        return bridge.call('refresh_saved', {'id':dataset_id})

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description='Arc MCP stdio server')
    parser.add_argument('--session-file', type=Path,
        default=Path(__file__).resolve().parents[1] / 'data' / 'mcp-session.json')
    args = parser.parse_args()
    create_server(args.session_file).run(transport='stdio')


if __name__ == '__main__':
    main()
