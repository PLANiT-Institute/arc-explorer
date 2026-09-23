"""Direct entry point usable from any MCP client's working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arc_explorer.mcp_server import main

if __name__ == '__main__':
    main()
