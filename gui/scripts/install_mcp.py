"""Install/register the local Arc MCP without storing login credentials."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Arc MCP installer')
    parser.add_argument('--client', choices=['codex','json'], default='codex')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    python = root / '.venv' / 'bin' / 'python'
    entry = root / 'gui' / 'scripts' / 'run_mcp.py'
    config = {'mcpServers': {'arc': {'command': str(python), 'args': [str(entry)]}}}
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return
    uv = shutil.which('uv')
    if not uv:
        uv = next((str(p) for p in [Path('/opt/homebrew/bin/uv'), Path.home()/'.local/bin/uv'] if p.exists()), None)
    if uv:
        subprocess.run([uv, 'sync', '--extra','dev','--extra','mcp'], cwd=root, check=True)
    else:
        if not python.exists():
            subprocess.run([sys.executable,'-m','venv',str(root/'.venv')],check=True)
        subprocess.run([str(python),'-m','ensurepip','--upgrade'],check=True)
        subprocess.run([str(python),'-m','pip','install','-e',str(root)+'[mcp]'],check=True)
    subprocess.run([str(python),str(entry),'--help'],check=True,stdout=subprocess.DEVNULL)
    target = root / 'gui' / 'data' / 'arc-mcp-config.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(config,indent=2)+'\n')
    if args.client == 'codex':
        codex = shutil.which('codex')
        if not codex:
            codex = next((str(p) for p in [Path('/Applications/ChatGPT.app/Contents/Resources/codex'), Path('/Applications/Codex.app/Contents/Resources/codex')] if p.exists()), None)
        if not codex:
            print(f'Codex CLI not found. Import this MCP configuration: {target}')
            return
        subprocess.run([codex,'mcp','add','arc','--',str(python),str(entry)],check=True)
        print('Arc MCP registered in Codex. Restart the MCP server/client to load its tools.')
    print(f'Generic MCP client configuration: {target}')
    print('Run arc.command and complete terminal password/MFA login. Keep it running while using Arc MCP.')


if __name__ == '__main__':
    main()
