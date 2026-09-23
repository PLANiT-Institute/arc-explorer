"""Local authenticated session discovery. Never stores Snowflake credentials."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


def publish(path: Path, url: str, token: str) -> None:
    """Publish a local, owner-readable session capability atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'url': url, 'token': token}, stream)
    temp.chmod(0o600)
    temp.replace(path)


class Bridge:
    """Forward MCP requests to the already signed-in local browser service."""

    def __init__(self, session_path: Path):
        self.session_path = session_path

    def call(self, action: str, payload: dict | None = None) -> dict:
        if action not in {'status','catalogue','relationships','lookup','query','companies','sql','saved','refresh_saved'}:
            raise ValueError('Unsupported bridge action')
        try:
            info = self.session_path.stat()
            if stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
                raise RuntimeError('MCP session file must belong to this user and have mode 0600. Restart arc.command.')
            session = json.loads(self.session_path.read_text())
            url = urlsplit(session['url'])
            if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.username or url.path not in ('','/'):
                raise RuntimeError('Invalid local Arc session address.')
            request = Request(session['url'].rstrip('/') + '/mcp/' + action,
                data=json.dumps(payload or {}).encode(), method='POST',
                headers={'Content-Type':'application/json','X-Arc-MCP-Token':session['token']})
            with build_opener(ProxyHandler({})).open(request, timeout=150) as response:
                return json.load(response)
        except FileNotFoundError as exc:
            raise RuntimeError('Run arc.command, finish password/MFA login, and keep the terminal open. No active Arc session.') from exc
        except HTTPError as exc:
            if exc.code in (401,403):
                raise RuntimeError('Arc session expired. Restart arc.command and sign in again.') from exc
            try:
                message = json.loads(exc.read()).get('error','Arc query failed')
            except (ValueError, AttributeError):
                message = 'Arc query failed'
            raise RuntimeError(message) from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError('Arc is not responding. Keep arc.command running; retry after login completes.') from exc
