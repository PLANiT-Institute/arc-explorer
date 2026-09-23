"""Authenticated local browser for the CLI's live Snowflake connection."""
from __future__ import annotations

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from arc_explorer.config import Settings
from arc_explorer.explorer_service import Explorer
from arc_explorer.linked_query import LinkedQuery
from arc_explorer.mcp_bridge import publish


def serve(conn, settings: Settings) -> None:
    """Start the explorer and retain the existing authenticated connection."""
    token = secrets.token_urlsafe(32)
    page = Path(__file__).with_name("explorer.html").read_text()
    explorer = Explorer(conn, settings, json.loads(settings.schema_cache_path.read_text()))
    linked = LinkedQuery(explorer)
    mcp_token = secrets.token_urlsafe(32)
    session_path = settings.schema_cache_path.parent / 'mcp-session.json'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json"):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/" or self.headers.get("Host") != address:
                self.reply(404, "{}")
                return
            self.reply(200, page, "text/html; charset=utf-8")

        def do_POST(self):
            mcp_request = self.path.startswith('/mcp/')
            authenticated = secrets.compare_digest(self.headers.get('X-Arc-MCP-Token', ''), mcp_token) if mcp_request else secrets.compare_digest(self.headers.get('X-Arc-Token', ''), token)
            if not authenticated or self.headers.get("Host") != address:
                self.reply(403, json.dumps({"error": "이 터미널에서 열린 브라우저를 사용하세요."}))
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("요청 크기가 너무 큽니다.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Request must be a JSON object')  # noqa: TRY004 - surfaced to the client as a 400, not a type contract
                if self.path == '/mcp/status':
                    result = {'connected': True, 'database':settings.database,'schema':settings.schema,'data_requires_sql':True}
                elif self.path == '/mcp/catalogue':
                    result = explorer.catalogue()
                    needle = str(data.get('search','')).lower()
                    result['tables'] = [t for t in result['tables'] if needle in t['name'].lower() or any(needle in c['name'].lower() for c in t['columns'])]
                    result['kind'] = 'cached_schema_metadata_only'
                elif self.path in ('/relationships','/mcp/relationships'):
                    result = linked.relationships(data['base_table'])
                elif self.path == '/mcp/lookup':
                    result = linked.lookup(**data)
                elif self.path == '/mcp/companies':
                    result = linked.companies(**data)
                elif self.path in ('/linked/preview','/linked/load','/mcp/query'):
                    if self.path == '/mcp/query':
                        result = linked.run(data['spec'], data.get('output','both'), data.get('save',False))
                    else:
                        result = linked.run(data, save=self.path.endswith('/load'))
                elif self.path in ('/sql', '/mcp/sql'):
                    result = explorer.run_sql(data['sql'], int(data.get('limit', 100)),
                        bool(data.get('save', False)), str(data.get('name', '')))
                elif self.path == '/mcp/saved':
                    result = {'datasets': explorer.saved(), 'kind':'local_snapshot_metadata_only'}
                elif self.path == '/mcp/refresh_saved':
                    saved = explorer.saved(data['id'])
                    if saved['spec'].get('_kind') == 'linked':
                        result = linked.run(saved['spec'])
                    elif saved['spec'].get('_kind') == 'sql':
                        result = explorer.run_sql(saved['spec']['sql'], saved['spec'].get('limit', 100))
                    else:
                        result = explorer.query(saved['spec'])
                        result['executed'] = True
                elif self.path == "/catalogue":
                    result = explorer.catalogue()
                elif self.path == "/preview":
                    result = explorer.query(data)
                elif self.path == "/load":
                    result = explorer.query(data, save=True)
                elif self.path == "/saved":
                    result = explorer.saved(data.get("id"))
                else:
                    self.reply(404, "{}")
                    return
                self.reply(200, json.dumps(result, default=str))
            except Exception as exc:  # noqa: BLE001 - request boundary: any handler error becomes a 400
                self.reply(400, json.dumps({"error": str(exc)}))

    server = HTTPServer(("127.0.0.1", settings.port), Handler)
    address = f"127.0.0.1:{server.server_port}"
    publish(session_path, f'http://{address}', mcp_token)
    print(f"Explorer ready at http://{address}/ — keep this terminal open. Ctrl+C stops it.")
    webbrowser.open(f"http://{address}/#{token}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        explorer.close()
        if session_path.exists():
            try:
                if json.loads(session_path.read_text()).get('token') == mcp_token:
                    session_path.unlink()
            except (OSError, ValueError):
                pass
