"""Package discovery entry point; JSONL transport is pending phase 4."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="driftlens-sql-agent",
        description="DriftLens SQL agent: bounded core available; JSONL transport not implemented.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {version('driftlens-sql-agent')}",
    )
    parser.add_argument("--config", type=Path, required=True, help="Runtime config path (future runtime)")
    parser.add_argument("--profile", type=Path, required=True, help="Business profile path (future runtime)")
    parser.add_argument("--protocol-version", choices=["v1"], default="v1")
    parser.parse_args(argv)
    print("transport_not_implemented: JSONL transport is not available yet; use the Python runtime API.", file=sys.stderr)
    return 2
