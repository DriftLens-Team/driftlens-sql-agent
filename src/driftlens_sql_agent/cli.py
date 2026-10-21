"""Package entry point. Phase 2 provides discovery, not a working runtime."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="driftlens-sql-agent",
        description="DriftLens SQL agent: package foundation; runtime not implemented.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {version('driftlens-sql-agent')}",
    )
    parser.add_argument("--config", type=Path, required=True, help="Runtime config path (future runtime)")
    parser.add_argument("--profile", type=Path, required=True, help="Business profile path (future runtime)")
    parser.add_argument("--protocol-version", choices=["v1"], default="v1")
    parser.parse_args(argv)
    print("runtime_not_implemented: SQL execution and JSONL transport are not available yet.", file=sys.stderr)
    return 2
