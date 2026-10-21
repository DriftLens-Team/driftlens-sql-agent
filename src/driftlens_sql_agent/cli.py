"""Validate startup once, then serve the v1 JSONL protocol."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys
import json

from .errors import AgentError
from .runtime import Runtime
from .settings import load_settings
from .transport import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="driftlens-sql-agent",
        description="DriftLens SQL agent: bounded read-only SQL over UTF-8 JSONL.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {version('driftlens-sql-agent')}",
    )
    parser.add_argument("--config", type=Path, required=True, help="Runtime config path")
    parser.add_argument("--profile", type=Path, required=True, help="Business profile path")
    parser.add_argument("--protocol-version", choices=["v1"], default="v1")
    args = parser.parse_args(argv)

    def diagnostic(event):
        sys.stderr.write(json.dumps(event, ensure_ascii=True) + "\n")
        sys.stderr.flush()

    try:
        runtime = Runtime(load_settings(args.config, args.profile))
    except AgentError:
        diagnostic({"stage": "startup", "code": "invalid_config"})
        return 2
    except Exception:
        diagnostic({"stage": "startup", "code": "internal_error"})
        return 1
    return serve(runtime, sys.stdin.buffer, sys.stdout.buffer, diagnostic)
