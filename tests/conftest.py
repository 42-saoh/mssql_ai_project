import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for rel in [
    ROOT / "apps" / "api",
    ROOT / "services" / "mssql-mcp",
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "analysis" / "src",
    ROOT / "packages" / "generation" / "src",
    ROOT / "packages" / "validation" / "src",
    ROOT / "packages" / "agent-runtime" / "src",
]:
    sys.path.insert(0, str(rel))
