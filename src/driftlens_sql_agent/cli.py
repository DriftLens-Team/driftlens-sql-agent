"""Validate startup once, then serve an explicitly selected JSONL protocol."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys
import json
import hashlib

from .errors import AgentError
from .runtime import Runtime
from .settings import load_settings
from .transport import serve


def main(argv: list[str] | None = None) -> int:
    """실행 진입점: 인자를 검증하고 실행 결과를 프로세스 종료 코드로 전달한다."""
    parser = argparse.ArgumentParser(
        prog="driftlens-sql-agent",
        description="DriftLens SQL agent: bounded read-only SQL over UTF-8 JSONL.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {version('driftlens-sql-agent')}",
    )
    parser.add_argument("--capabilities", action="store_true", help="Print protocol and schema support without loading credentials")
    parser.add_argument("--config", type=Path, help="Runtime config path")
    parser.add_argument("--profile", type=Path, help="Business profile path")
    parser.add_argument("--protocol-version", choices=["v1", "v2"], default="v1")
    args = parser.parse_args(argv)
    if args.capabilities:
        from .semalign import UNITS
        from .provider import GENERATION
        root = Path(__file__).parent
        source = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.suffix in {".py", ".txt"}:
                source.update(path.relative_to(root).as_posix().encode("utf-8"))
                source.update(path.read_bytes())
        print(json.dumps({"protocols": ["agent/v1", "agent/v2"], "schemas": ["semalign/v1"],
                          "concepts": sorted(UNITS), "definition_note_origin": "profile_rendered",
                          "package_version": version("driftlens-sql-agent"), "implementation_sha256": source.hexdigest(),
                          "prompt_sha256": hashlib.sha256((root / "prompts/semalign.txt").read_bytes()).hexdigest(),
                          "generation": GENERATION}))
        return 0
    if args.config is None or args.profile is None:
        parser.error("--config and --profile are required when serving requests")

    def diagnostic(event):
        """진단 콜백: 응답 스트림과 분리된 stderr에 허용된 메타데이터만 쓴다."""
        sys.stderr.write(json.dumps(event, ensure_ascii=True) + "\n")
        sys.stderr.flush()

    try:
        runtime = Runtime(load_settings(args.config, args.profile, protocol=args.protocol_version))
    except AgentError:
        diagnostic({"stage": "startup", "code": "invalid_config"})
        return 2
    except Exception:
        diagnostic({"stage": "startup", "code": "internal_error"})
        return 1
    return serve(runtime, sys.stdin.buffer, sys.stdout.buffer, diagnostic)
