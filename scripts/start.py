"""F5와 터미널에서 동일한 설정 선택 후 실제 JSONL CLI를 시작한다."""

import json
import os
from pathlib import Path
import re
import runpy
import sys
import tempfile

from driftlens_sql_agent.cli import main as cli_main


def main():
    """실행 진입점: 자격 증명을 검증하고 준비된 DB로 실제 CLI를 호출한다."""
    root = Path(__file__).resolve().parents[1]
    names = ("UPSTAGE_MODEL", "UPSTAGE_API_KEY")
    values = {}
    temporary = None
    try:
        env_file = root / ".env"
        if env_file.exists():
            # 의도적으로 작은 문법만 지원한다. 비밀값이나 잘못된 원문을 오류에 넣지 않는다.
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)", line)
                if not match:
                    raise ValueError("Invalid .env format; use KEY=VALUE.")
                name, value = match.groups()
                if name not in names:
                    continue
                if name in values:
                    raise ValueError("Duplicate model setting in .env.")
                value = value.strip()
                if value.startswith(("'", '"')):
                    if len(value) < 2 or value[-1] != value[0]:
                        raise ValueError("Unclosed quote in .env.")
                    value = value[1:-1]
                values[name] = value
        # 빈 문자열도 명시적 설정이다. 부모 환경의 값을 .env로 가리지 않는다.
        values.update({name: os.environ[name] for name in names if name in os.environ})
        if not values:
            provider = "fake"
        elif all(values.get(name, "").strip() for name in names):
            provider = "upstage"
        else:
            missing = ", ".join(name for name in names if not values.get(name, "").strip())
            print("Set non-empty values for: " + missing, file=sys.stderr)
            return 2
        os.environ.update(values)

        runpy.run_path(str(root / "scripts/prepare_debug.py"))
        config_path = root / "runs/local-debug/runtime.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        # 상대 DB 경로를 유지하도록 같은 디렉터리에 실행용 설정만 만든다.
        config["model"] = {"provider": provider, "id_env": names[0], "api_key_env": names[1]}
        db_path = (config_path.parent / config["database"]["path"]).resolve()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                         prefix="session-", dir=config_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream)
        print(f"Model: {provider} | DB: {db_path}", file=sys.stderr, flush=True)
        # 실제 CLI의 반환값을 유지하고 API 오류를 다른 모델로 대체하지 않는다.
        return cli_main(["--config", str(temporary), "--profile",
                         str(root / "profiles/v1/profile.example.json"), "--protocol-version", "v1"])
    except (OSError, ValueError, KeyError, TypeError):
        # 설정 파일이나 자격 증명을 포함할 수 있는 예외 원문은 출력하지 않는다.
        print("Startup configuration error. Check .env: set both UPSTAGE_MODEL and UPSTAGE_API_KEY "
              "to non-empty values, or remove both to use fake. Check local DB/config files.", file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
