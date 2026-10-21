"""Real temporary SQLite, isolated model doubles, no provider calls."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from driftlens_sql_agent.errors import AgentError, ModelError
from driftlens_sql_agent.runtime import Runtime
from driftlens_sql_agent.schemas import Request, strict_json
from driftlens_sql_agent.settings import Budgets, Profile, Settings, load_settings, MAPPING
from driftlens_sql_agent.sql_access import query, validate_database
from driftlens_sql_agent.validation import answer_value, count_value


ROWS = [("2025-01-12", 5000), ("2025-01-13", 1999), ("2025-01-13", 2000),
        ("2025-01-14", 2001), ("2025-01-15", 2999), ("2025-01-16", 3000),
        ("2025-01-19", 3001), ("2025-01-20", 5000), ("2025-01-21", 3000),
        ("2025-01-26", 2000)]
REQUEST = {"request_id": "req-1", "request": "이번 주 대형 주문은 몇 건인가요?",
           "timestamp": "2025-01-19T23:59:59Z", "period": "2025-W03"}
SQL = "SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND ordered_at < '2025-01-20' AND order_total_cents >= 3000"
QUERY = {"action": "query", "sql": SQL}
ANSWER = {"action": "answer", "answer_text": "이번 주 대형 주문은 2건입니다."}


class ScriptedModel:
    def __init__(self, actions):
        """생성자 훅: 이 인스턴스의 실행 상태와 검증된 의존성을 준비한다."""
        self.actions = actions
        self.index = 0

    def generate(self, messages, *, timeout, max_bytes):
        """모델 교체 인터페이스: worker가 지정한 입력과 제한으로 다음 action을 반환한다."""
        action = self.actions[self.index]
        self.index += 1
        if isinstance(action, dict) and "raise_model" in action:
            raise ModelError(action["raise_model"], transient=action.get("transient", False),
                             retry_after=action.get("retry_after", 0))
        if isinstance(action, dict) and "sleep" in action:
            time.sleep(action["sleep"])
            return {"action": "unsupported"}
        if isinstance(action, dict) and "inspect" in action:
            assert len(messages) == 2
            assert "api_key" not in str(messages) and "SECRET" not in str(messages)
            return {"action": "unsupported"}
        return action


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        """unittest 준비 훅: 각 테스트가 독립된 데이터와 자원을 사용하게 한다."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "orders.sqlite"
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)")
            connection.executemany("INSERT INTO orders VALUES(?,?,?)", [(str(i), *row) for i, row in enumerate(ROWS)])
            connection.execute("CREATE TABLE private_truth(secret TEXT)")
        connection.close()
        self.settings = Settings(self.db, Profile(3000), Budgets(), "fake")


class SettingsTests(DatabaseCase):
    def setUp(self):
        """unittest 준비 훅: 각 테스트가 독립된 데이터와 자원을 사용하게 한다."""
        super().setUp()
        (self.root / "configs").mkdir()
        self.config_path = self.root / "configs/runtime.json"
        self.profile_path = self.root / "profile.json"
        self.config = {"database": {"kind": "sqlite", "path": "../orders.sqlite", "read_only": True},
                       "schema_mapping": MAPPING, "amount_unit": "integer_cents",
                       "model": {"provider": "fake", "id_env": "MODEL", "api_key_env": "KEY"}}
        self.profile = Profile(3000).definition()

    def load(self, env=None):
        """변형한 설정과 profile을 파일에 써서 실제 로더의 검증을 실행한다."""
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        return load_settings(self.config_path, self.profile_path, environ=env or {})

    def test_relative_path_defaults_and_secret_repr(self):
        """상대 DB 경로·기본 예산·비밀값 비노출을 확인한다."""
        settings = self.load()
        self.assertTrue(settings.db_path.samefile(self.db))
        self.assertEqual(settings.budgets.max_model_calls, 5)
        self.config["model"]["provider"] = "upstage"
        with self.assertRaisesRegex(AgentError, "Invalid startup"):
            self.load()
        settings = self.load({"MODEL": "model-name", "KEY": "SECRET"})
        self.assertNotIn("SECRET", repr(settings))

    def test_config_invalid_values(self):
        """설정의 오타·잘못된 타입·상한 초과를 거부하는지 확인한다."""
        original = json.loads(json.dumps(self.config))
        variants = [
            {**original, "extra": True}, {**original, "amount_unit": "dollars"},
            {**original, "schema_mapping": {**MAPPING, "table": "private_truth"}},
            {**original, "database": {**original["database"], "read_only": 1}},
            {**original, "database": {**original["database"], "path": "missing.sqlite"}},
            {**original, "budgets": {"max_model_calls": True}},
            {**original, "budgets": {"request_timeout_seconds": 61}},
            {**original, "budgets": {"unknown": 1}},
        ]
        for value in variants:
            with self.subTest(value=value):
                self.config = value
                with self.assertRaises(AgentError):
                    self.load()

    def test_profiles_and_duplicate_json(self):
        """임계값 타입과 JSON 중복 키를 검증한다."""
        for value in [True, -1, 2.5, "3000"]:
            self.profile["threshold"] = value
            with self.assertRaises(AgentError):
                self.load()
        self.config_path.write_text('{"x":1,"x":2}')
        with self.assertRaises(AgentError):
            load_settings(self.config_path, self.profile_path)
        self.assertEqual(Budgets(action_repair_attempts=0).action_repair_attempts, 0)


class SchemaTests(unittest.TestCase):
    def test_time_normalization_and_iso_year(self):
        """시간대 정규화와 연도를 넘는 ISO 주간을 확인한다."""
        for stamp in ["2025-01-19T23:59:59Z", "2025-01-20T08:59:59+09:00", "2025-01-19T23:59:59"]:
            parsed = Request.parse({**REQUEST, "timestamp": stamp})
            self.assertEqual(parsed.start, date(2025, 1, 13))
            self.assertEqual(parsed.assumed_utc, stamp.endswith("59"))
        parsed = Request.parse({**REQUEST, "period": "2020-W53", "timestamp": "2021-01-03T23:59:59Z"})
        self.assertEqual(parsed.start, date(2020, 12, 28))

    def test_request_errors(self):
        """유효하지 않은 업무 필드와 프로토콜 ID 오류를 구분한다."""
        for patch in [{"period": "2025-W53"}, {"timestamp": "2025-01-19T23:59:58Z"},
                      {"timestamp": "2025-01-19T23:59:59.0Z"}, {"request": " "},
                      {"request": "x" * 4097}, {"profile": "v2"}, {"period": 1}]:
            with self.subTest(patch=patch), self.assertRaises(AgentError) as caught:
                Request.parse({**REQUEST, **patch})
            self.assertEqual(caught.exception.code, "invalid_request")
        with self.assertRaises(AgentError) as caught:
            Request.parse({**REQUEST, "request_id": "bad id"})
        self.assertEqual(caught.exception.code, "protocol_error")

    def test_strict_json_actions_and_answers(self):
        """JSON과 관측 건수·답변의 형식 위반을 거부하는지 확인한다."""
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}']:
            with self.assertRaises(ValueError):
                strict_json(raw)
        for text in ["이번 주 대형 주문은 3건입니다.", "3000센트 이상 2건", "2건 v2", "2건 2건"]:
            with self.assertRaises(AgentError):
                answer_value(text, 2)
        for rows in [[], [[True]], [[2.0]], [[None]], [[-1]], [[1, 2]], [[1], [2]]]:
            with self.assertRaises(AgentError):
                count_value({"rows": rows})


class SqlTests(DatabaseCase):
    def query(self, sql, budgets=None):
        """여러 SQL 사례를 같은 테스트 DB와 기한으로 실행한다."""
        return query(self.db, sql, budgets or Budgets(), deadline=time.monotonic() + 10)

    def test_readonly_and_function_boundaries(self):
        """쓰기·비공개 테이블·허용되지 않은 함수 접근을 거부한다."""
        for sql in ["DELETE FROM orders", "CREATE TABLE bad(x)", "PRAGMA table_info(orders)",
                    "ATTACH DATABASE ':memory:' AS x", "SELECT * FROM private_truth",
                    "SELECT * FROM sqlite_master", "SELECT load_extension('x')",
                    "SELECT SUM(order_total_cents) FROM orders", "SELECT 1; SELECT 2"]:
            with self.subTest(sql=sql), self.assertRaises(AgentError):
                self.query(sql)
        self.assertEqual(self.query("SELECT COUNT(*) FROM orders")["rows"], [(10,)])

    def test_limits_and_schema(self):
        """SQL 실행량·길이·행 수와 실제 테이블 스키마 제한을 확인한다."""
        with self.assertRaises(AgentError):
            self.query(SQL, Budgets(sql_max_chars=5))
        with self.assertRaises(AgentError):
            self.query("SELECT * FROM orders", Budgets(sql_max_rows=1))
        with self.assertRaises(AgentError):
            self.query("SELECT COUNT(*) FROM orders a, orders b, orders c, orders d, orders e, orders f", Budgets(sql_vm_steps=100))
        with self.assertRaises(AgentError) as caught:
            query(self.db, SQL, Budgets(), deadline=time.monotonic() - 1)
        self.assertEqual(caught.exception.code, "request_timeout")
        missing = self.root / "missing.sqlite"
        with self.assertRaises(AgentError):
            validate_database(missing)
        self.assertFalse(missing.exists())
        with sqlite3.connect(self.db) as db:
            db.execute("ALTER TABLE orders ADD COLUMN extra TEXT")
        db.close()
        with self.assertRaises(AgentError) as caught:
            validate_database(self.db)
        self.assertEqual(caught.exception.code, "invalid_config")

    def test_sql_deadline_precedes_sql_error(self):
        """기계 속도와 무관하게 전체 요청 기한 오류의 우선순위를 검증한다."""
        from unittest.mock import patch
        # Simulate elapsed time during a query, independent of machine speed.
        with patch("driftlens_sql_agent.sql_access.time.monotonic", side_effect=[0, 0, 0, 11, 11]):
            with self.assertRaises(AgentError) as caught:
                query(self.db, SQL, Budgets(), deadline=10)
        self.assertEqual(caught.exception.code, "request_timeout")
        with patch("driftlens_sql_agent.sql_access.time.monotonic", side_effect=[0, 0, 0, 3, 3]):
            with self.assertRaises(AgentError) as caught:
                query(self.db, SQL, Budgets(), deadline=10)
        self.assertEqual(caught.exception.code, "sql_error")

    def test_locked_database_returns_promptly(self):
        """DB 잠금 때문에 요청이 장시간 대기하지 않는지 확인한다."""
        with sqlite3.connect(self.db) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(AgentError):
                self.query(SQL)
            self.assertLess(time.monotonic() - started, 1)
        lock.close()

    def test_profile_and_period_boundary_counts(self):
        """시작일 포함·종료일 제외·임계값 이상 조건을 확인한다."""
        for start, end, values in [("2025-01-13", "2025-01-20", [5, 2]), ("2025-01-20", "2025-01-27", [3, 2])]:
            for threshold, expected in zip([2000, 3000], values):
                sql = f"SELECT COUNT(*) FROM orders WHERE ordered_at >= '{start}' AND ordered_at < '{end}' AND order_total_cents >= {threshold}"
                self.assertEqual(count_value(self.query(sql)), expected)
        baseline = count_value(self.query(SQL))
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO orders VALUES('outside','2025-01-20',3000)")
        db.close()
        self.assertEqual(count_value(self.query(SQL)), baseline)
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO orders VALUES('equal','2025-01-19',3000)")
        db.close()
        self.assertEqual(count_value(self.query(SQL)), baseline + 1)


class RuntimeTests(DatabaseCase):
    def scripted(self, actions, budgets=None):
        """재시도·복구·기한 테스트에 필요한 모델 응답 순서를 주입한다."""
        return Runtime(replace(self.settings, budgets=budgets or Budgets()), ScriptedModel(actions))

    def test_fake_profile_switch_and_isolation(self):
        """profile 변경을 반영하고 이전 요청의 모델 상태를 재사용하지 않는지 확인한다."""
        for threshold, expected in [(2000, 5), (3000, 2)]:
            runtime = Runtime(replace(self.settings, profile=Profile(threshold)))
            for _ in range(2):
                result = runtime.run(REQUEST)
                self.assertEqual(result["observation"]["reported_values"][0]["value"], expected)
                self.assertEqual(set(result["observation"]), {"sql", "answer_text", "definition_note", "reported_values", "referenced_concepts"})
        # Each request gets a new worker, even when the parent model carries an index.
        runtime = self.scripted([{"inspect": True}])
        self.assertEqual(runtime.run(REQUEST)["error"]["code"], "unsupported_request")
        self.assertEqual(runtime.run(REQUEST)["error"]["code"], "unsupported_request")

    def test_invalid_actions_at_worker_boundary(self):
        """잘못된 action이 프로세스 경계에서 고정 오류로 변환되는지 확인한다."""
        for action in [[], {"action": []}, {"action": "query", "sql": 5},
                       {**ANSWER, "truth": True}, "x" * 65537, '{"action":"answer","action":"query"}']:
            with self.subTest(action=str(action)[:80]):
                result = self.scripted([action], Budgets(action_repair_attempts=0)).run(REQUEST)
                self.assertEqual(result["error"]["code"], "invalid_action")

    def test_repair_and_invalidated_observation(self):
        """복구 후 이전 SQL 관측을 잘못 재사용하지 않는지 확인한다."""
        result = self.scripted([{"action": "query", "sql": "DELETE FROM orders"}, QUERY, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        for bad in [{"action": "query", "sql": "SELECT * FROM private_truth"}, {"action": "oops"}]:
            result = self.scripted([QUERY, bad, ANSWER]).run(REQUEST)
            self.assertEqual(result["error"]["code"], "answer_validation_failed")
        result = self.scripted([QUERY, {"action": "answer", "answer_text": "3건"}, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")

    def test_model_retry_and_auth_no_fallback(self):
        """일시 오류만 제한적으로 재시도하고 인증 실패는 숨기지 않는지 확인한다."""
        result = self.scripted([{"raise_model": "model_request_failed", "transient": True}, QUERY, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        for error in [{"raise_model": "model_auth_failed"},
                      {"raise_model": "model_request_failed", "transient": True, "retry_after": 2}]:
            result = self.scripted([error]).run(REQUEST)
            self.assertEqual(result["error"]["code"], error["raise_model"])
        failure = {"raise_model": "model_request_failed", "transient": True}
        result = self.scripted([failure, failure, QUERY]).run(REQUEST)
        self.assertEqual(result["error"]["code"], "model_request_failed")
        result = self.scripted([failure, {"action": "bad"}], Budgets(max_model_calls=2)).run(REQUEST)
        self.assertEqual(result["error"]["code"], "turn_limit")

    def test_generated_sql_semantic_variations(self):
        """빈 데이터·기간 밖·임계값 경계·연도 경계에서 생성 SQL을 검증한다."""
        cases = [
            ([], "2025-W03", "2025-01-19T23:59:59Z", 0),
            ([("2025-01-15", 2999)], "2025-W03", "2025-01-19T23:59:59Z", 0),
            ([("2025-01-15", 2999), ("2025-01-15", 3000), ("2025-01-15", 3001)], "2025-W03", "2025-01-19T23:59:59Z", 2),
            ([("2025-01-12", 5000), ("2025-01-20", 5000)], "2025-W03", "2025-01-19T23:59:59Z", 0),
            ([("2020-12-28", 3000), ("2021-01-03", 3001), ("2021-01-04", 5000)], "2020-W53", "2021-01-03T23:59:59Z", 2),
        ]
        for rows, period, stamp, expected in cases:
            with self.subTest(period=period, rows=rows):
                with sqlite3.connect(self.db) as db:
                    db.execute("DELETE FROM orders")
                    db.executemany("INSERT INTO orders VALUES(?,?,?)", [(str(i), *r) for i, r in enumerate(rows)])
                db.close()
                result = Runtime(self.settings).run({**REQUEST, "period": period, "timestamp": stamp})
                self.assertEqual(result["observation"]["reported_values"][0]["value"], expected)

    def test_call_limits_and_final_call_success(self):
        """마지막 허용 호출의 성공을 인정하고 초과 호출은 막는지 확인한다."""
        result = self.scripted([QUERY, ANSWER], Budgets(max_model_calls=2)).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        result = self.scripted([QUERY], Budgets(max_model_calls=1)).run(REQUEST)
        self.assertEqual(result["error"]["code"], "turn_limit")
        result = self.scripted([{"action": "bad"}], Budgets(action_repair_attempts=0)).run(REQUEST)
        self.assertEqual(result["error"]["code"], "invalid_action")

    def test_uncooperative_model_deadlines(self):
        """모델이 timeout을 무시해도 부모가 프로세스를 중단하는지 확인한다."""
        for budgets, expected in [(Budgets(model_timeout_seconds=1, model_transient_retries=0), "model_timeout"),
                                  (Budgets(request_timeout_seconds=1), "request_timeout")]:
            started = time.monotonic()
            result = self.scripted([{"sleep": 30}], budgets).run(REQUEST)
            self.assertEqual(result["error"]["code"], expected)
            self.assertLess(time.monotonic() - started, 3)

    def test_diagnostics_are_metadata_only(self):
        """진단에 SQL·임계값·요청 본문이 노출되지 않는지 확인한다."""
        events = []
        runtime = Runtime(self.settings)
        result = runtime.run({**REQUEST, "timestamp": "2025-01-19T23:59:59"}, diagnostic=events.append)
        self.assertEqual(result["status"], "ok")
        self.assertIn("timestamp_assumed_utc", [e["stage"] for e in events])
        for event in events:
            self.assertLessEqual(set(event), {"request_id", "stage", "elapsed_ms", "code"})
        self.assertNotIn("3000", json.dumps(events))
        self.assertNotIn("SELECT", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
