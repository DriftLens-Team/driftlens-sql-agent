"""Fixed 60-case evaluation through installed CLI; artifacts stay under private runs/."""

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from driftlens_sql_agent.errors import MESSAGES
from driftlens_sql_agent.provider import GENERATION
from driftlens_sql_agent.schemas import strict_json
from driftlens_sql_agent.settings import Budgets, MAPPING, Profile
from driftlens_sql_agent.sql_access import query
from driftlens_sql_agent.validation import answer_value, count_value
from .cases import ROWS, corpus, expected


ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    """평가 입력과 실행 코드가 바뀌지 않았는지 비교할 SHA-256 값을 계산한다."""
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    """평가 파일의 해시와 저장 내용이 일치하도록 키 순서·인코딩을 고정한다."""
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")


def score(case, response, *, secret="", private_markers=()):
    """응답 계약과 정보 노출을 검사하고 변형 DB에서 SQL 의미를 재검증한다."""
    result = {"passed": False, "protocol_ok": False, "information_ok": False,
              "semantic_ok": False, "reason": "protocol"}
    try:
        serialized = encode(response).decode("utf-8")
        if (secret and secret in serialized) or any(marker and marker in serialized for marker in private_markers):
            result["reason"] = "information_boundary"
            return result
        if type(response) is not dict or response.get("request_id") != case["request"]["request_id"]:
            return result
        if response.get("status") == "error":
            error = response["error"]
            if (set(response) != {"request_id", "status", "error"} or type(error) is not dict
                    or set(error) != {"code", "message"} or type(error["code"]) is not str
                    or error["code"] not in MESSAGES or error["message"] != MESSAGES[error["code"]]):
                return result
            result.update(protocol_ok=True, information_ok=True, reason=error["code"])
            result["passed"] = not case["supported"] and error["code"] == "unsupported_request"
            return result
        if response.get("status") != "ok" or set(response) != {"request_id", "status", "observation"}:
            return result
        observation = response["observation"]
        if type(observation) is not dict or set(observation) != {
            "sql", "answer_text", "definition_note", "reported_values", "referenced_concepts"
        }:
            return result
        values = observation["reported_values"]
        if (type(values) is not list or len(values) != 1 or type(values[0]) is not dict
                or set(values[0]) != {"concept_id", "value", "period"}
                or values[0]["concept_id"] != "large_orders" or type(values[0]["value"]) is not int
                or values[0]["value"] < 0 or values[0]["period"] != case["request"]["period"]
                or observation["referenced_concepts"] != ["large_orders"]
                or any(type(observation[key]) is not str for key in ["sql", "answer_text", "definition_note"])):
            return result
        result["protocol_ok"] = True
        answer_value(observation["answer_text"], values[0]["value"])
        if observation["definition_note"] != f"주문 총액 {case['threshold']}센트 이상인 주문":
            result["reason"] = "information_boundary"
            return result
        result["information_ok"] = True
        if not case["supported"]:
            result["reason"] = "unsupported_accepted"
            return result
        period, threshold = case["request"]["period"], case["threshold"]
        if values[0]["value"] != expected(ROWS, period, threshold):
            result["reason"] = "wrong_count"
            return result
        year, week = period.split("-W")
        first = date.fromisocalendar(int(year), int(week), 1)
        start, end = str(first), str(first + timedelta(days=7))
        datasets = [[], [(start, threshold - 1)], ROWS + [(start, threshold)],
                ROWS + [(end, threshold + 1)], ROWS + [(start, threshold - 1)],
                ROWS + [(start, threshold + 1)]]
        with tempfile.TemporaryDirectory() as folder:
            for index, rows in enumerate([ROWS, *datasets]):
                path = Path(folder) / f"variant-{index}.sqlite"
                # SQL의 경계 조건을 구별하는 데이터로 매번 새 DB를 만든다.
                with sqlite3.connect(path) as db:
                    db.execute("CREATE TABLE orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)")
                    db.executemany("INSERT INTO orders VALUES(?,?,?)", [(f"row-{i}", *row) for i, row in enumerate(rows)])
                db.close()
                value = count_value(query(path, observation["sql"], Budgets(), deadline=time.monotonic() + 3))
                if value != expected(rows, period, threshold):
                    result["reason"] = "sql_semantics"
                    return result
        result.update(passed=True, semantic_ok=True, reason="ok")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        result["reason"] = "invalid_observation"
    return result


def main():
    """실행 진입점: 인자를 검증하고 실행 결과를 프로세스 종료 코드로 전달한다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["upstage", "fake"], default="upstage")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        provider, output = args.provider, args.output
        model_id = os.environ.get("UPSTAGE_MODEL") if provider == "upstage" else "fake"
        secret = os.environ.get("UPSTAGE_API_KEY", "") if provider == "upstage" else ""
        if provider == "upstage" and (not model_id or not model_id.strip() or not secret.strip()):
            raise ValueError("UPSTAGE_MODEL and UPSTAGE_API_KEY must be configured")
        output = output.resolve()
        output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier evaluation.
        cases = corpus()
        db_path = output / "fixture.sqlite"
        # 원본 fixture와 의미 검증용 변형 DB는 수명과 용도가 달라 각각 생성한다.
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)")
            db.executemany("INSERT INTO orders VALUES(?,?,?)", [(f"row-{i}", *row) for i, row in enumerate(ROWS)])
        db.close()
        baseline_db = digest(db_path.read_bytes())
        config = {"database": {"kind": "sqlite", "path": "fixture.sqlite", "read_only": True},
                  "schema_mapping": MAPPING, "amount_unit": "integer_cents",
                  "model": {"provider": provider, "id_env": "UPSTAGE_MODEL", "api_key_env": "UPSTAGE_API_KEY"},
                  "budgets": asdict(Budgets())}
        config_path = output / "runtime.json"
        config_path.write_bytes(encode(config))
        for threshold in [2000, 3000]:
            (output / f"profile-{threshold}.json").write_bytes(encode(Profile(threshold).definition()))
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
        source_hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes())
                         for parent in [ROOT / "src", ROOT / "evaluation"]
                         for p in sorted(parent.rglob("*")) if p.is_file() and p.suffix in {".py", ".txt"}}
        # Evaluate exactly the runtime whose source hashes are recorded, even with a wheel install.
        for path in (ROOT / "src/driftlens_sql_agent").rglob("*"):
            if path.is_file() and path.suffix in {".py", ".txt"}:
                installed = files("driftlens_sql_agent").joinpath(str(path.relative_to(ROOT / "src/driftlens_sql_agent")))
                if digest(installed.read_bytes()) != digest(path.read_bytes()):
                    raise ValueError("Installed runtime differs from this checkout; reinstall before evaluation")
        manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "provider": provider,
                    "model_id": model_id, "generation": GENERATION, "code_commit": revision, "dirty_tree": dirty,
                    "source_hashes": source_hashes, "protocol": "v1", "budgets": asdict(Budgets()),
                    "prompt_sha256": digest(files("driftlens_sql_agent").joinpath("prompts/system.txt").read_bytes()),
                    "db_sha256": baseline_db, "config_sha256": digest(encode(config)),
                    "profiles": {str(t): digest(encode(Profile(t).definition())) for t in [2000, 3000]},
                    "corpus_sha256": digest(encode(cases)), "cases": cases, "fixture": ROWS,
                    "repetitions": 3, "gate": {"supported_min": 33, "unsupported_required": 24,
                                               "violations_allowed": 0}}
        (output / "manifest.private.json").write_bytes(encode(manifest))  # Freeze before the first model call.
        records = []
        private_markers = [manifest["prompt_sha256"], manifest["db_sha256"], *manifest["profiles"].values(),
                           "ontology_version_used", "contaminated", "truth.jsonl", "profile_id",
                           "profile-2000", "profile-3000"]
        with (output / "results.private.jsonl").open("wb") as results_file:
            for repetition in range(3):
                for case in cases:
                    started = time.monotonic()
                    command = [sys.executable, "-m", "driftlens_sql_agent", "--config", str(config_path),
                               "--profile", str(output / f"profile-{case['threshold']}.json")]
                    response, events = None, []
                    checks = {"passed": False, "protocol_ok": False, "information_ok": False,
                              "semantic_ok": False, "reason": "process_failure"}
                    try:
                        process = subprocess.run(command, input=encode(case["request"]) + b"\n", capture_output=True,
                                                 timeout=70, cwd=ROOT)
                        lines = process.stdout.splitlines()
                        if process.returncode == 0 and len(lines) == 1 and len(lines[0]) <= 65536:
                            response = strict_json(lines[0].decode("utf-8"))
                            checks = score(case, response, secret=secret, private_markers=private_markers)
                        events = [strict_json(row) for row in process.stderr.decode("utf-8").splitlines()]
                        if any(type(e) is not dict or set(e) - {"request_id", "stage", "elapsed_ms", "code"} for e in events):
                            checks.update(passed=False, information_ok=False, reason="diagnostic_boundary")
                        if secret and secret.encode() in process.stderr:
                            checks.update(passed=False, information_ok=False, reason="diagnostic_boundary")
                    except subprocess.TimeoutExpired:
                        checks["reason"] = "parent_timeout"
                    except (ValueError, UnicodeError, RecursionError):
                        checks.update(passed=False, protocol_ok=False, reason="protocol")
                    unchanged = digest(db_path.read_bytes()) == baseline_db
                    if not unchanged:
                        checks.update(passed=False, reason="db_modified")
                    record = {"case_id": case["request"]["request_id"], "repetition": repetition + 1,
                              "supported": case["supported"], "elapsed_ms": round((time.monotonic() - started) * 1000),
                              "model_calls": sum(type(e) is dict and e.get("stage") == "model_call" for e in events),
                              "db_unchanged": unchanged, **checks}
                    # Only validated safe observations are retained for reproducing semantic failures.
                    if checks["information_ok"] and type(response) is dict and response.get("status") == "ok":
                        record["observation"] = response["observation"]
                    # Raw provider responses, stderr and credentials are never persisted.
                    results_file.write(encode(record) + b"\n")
                    results_file.flush()
                    records.append(record)
                    print(f"{len(records)}/60 {record['case_id']} {record['reason']}", flush=True)
        supported = sum(r["passed"] for r in records if r["supported"])
        refused = sum(r["passed"] for r in records if not r["supported"])
        violations = sum(not r["protocol_ok"] or not r["information_ok"] or not r["db_unchanged"] for r in records)
        gate_passed = supported >= 33 and refused == 24 and violations == 0
        summary = {"provider": provider, "total": 60, "supported_passed": supported, "supported_total": 36,
                   "unsupported_refused": refused, "unsupported_total": 24, "violations": violations,
                   "reasons": dict(Counter(r["reason"] for r in records)), "gate_passed": gate_passed,
                   "live_quality_verified": provider == "upstage" and gate_passed,
                   "mean_latency_ms": round(sum(r["elapsed_ms"] for r in records) / len(records)),
                   "model_calls": sum(r["model_calls"] for r in records)}
        (output / "summary.private.json").write_bytes(encode(summary))
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
