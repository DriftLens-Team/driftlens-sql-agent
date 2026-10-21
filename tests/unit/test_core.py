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
from driftlens_sql_agent.validation import action_value, answer_value, count_value


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
        self.actions = actions
        self.index = 0

    def generate(self, messages, *, timeout, max_bytes):
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
        super().setUp()
        (self.root / "configs").mkdir()
        self.config_path = self.root / "configs/runtime.json"
        self.profile_path = self.root / "profile.json"
        self.config = {"database": {"kind": "sqlite", "path": "../orders.sqlite", "read_only": True},
                       "schema_mapping": MAPPING, "amount_unit": "integer_cents",
                       "model": {"provider": "fake", "id_env": "MODEL", "api_key_env": "KEY"}}
        self.profile = Profile(3000).definition()

    def load(self, env=None):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        return load_settings(self.config_path, self.profile_path, environ=env or {})

    def test_relative_path_defaults_and_secret_repr(self):
        settings = self.load()
        self.assertEqual(settings.db_path, self.db)
        self.assertEqual(settings.budgets.max_model_calls, 5)
        self.config["model"]["provider"] = "upstage"
        with self.assertRaisesRegex(AgentError, "Invalid startup"):
            self.load()
        settings = self.load({"MODEL": "model-name", "KEY": "SECRET"})
        self.assertNotIn("SECRET", repr(settings))

    def test_config_invalid_values(self):
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
        for stamp in ["2025-01-19T23:59:59Z", "2025-01-20T08:59:59+09:00", "2025-01-19T23:59:59"]:
            parsed = Request.parse({**REQUEST, "timestamp": stamp})
            self.assertEqual(parsed.start, date(2025, 1, 13))
            self.assertEqual(parsed.assumed_utc, stamp.endswith("59"))
        parsed = Request.parse({**REQUEST, "period": "2020-W53", "timestamp": "2021-01-03T23:59:59Z"})
        self.assertEqual(parsed.start, date(2020, 12, 28))

    def test_request_errors(self):
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
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}']:
            with self.assertRaises(ValueError):
                strict_json(raw)
        for action in [[], {"action": []}, {"action": "query", "sql": 5},
                       {**ANSWER, "truth": True}, "x" * 65537, '{"action":"answer","action":"query"}']:
            with self.assertRaises(AgentError):
                action_value(action)
        for text in ["이번 주 대형 주문은 3건입니다.", "3000센트 이상 2건", "2건 v2", "2건 2건"]:
            with self.assertRaises(AgentError):
                answer_value(text, 2)
        for rows in [[], [[True]], [[2.0]], [[None]], [[-1]], [[1, 2]], [[1], [2]]]:
            with self.assertRaises(AgentError):
                count_value({"rows": rows})


class SqlTests(DatabaseCase):
    def query(self, sql, budgets=None):
        return query(self.db, sql, budgets or Budgets(), deadline=time.monotonic() + 10)

    def test_readonly_and_function_boundaries(self):
        for sql in ["DELETE FROM orders", "CREATE TABLE bad(x)", "PRAGMA table_info(orders)",
                    "ATTACH DATABASE ':memory:' AS x", "SELECT * FROM private_truth",
                    "SELECT * FROM sqlite_master", "SELECT load_extension('x')",
                    "SELECT SUM(order_total_cents) FROM orders", "SELECT 1; SELECT 2"]:
            with self.subTest(sql=sql), self.assertRaises(AgentError):
                self.query(sql)
        self.assertEqual(self.query("SELECT COUNT(*) FROM orders")["rows"], [(10,)])

    def test_limits_and_schema(self):
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

    def test_locked_database_returns_promptly(self):
        with sqlite3.connect(self.db) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(AgentError):
                self.query(SQL)
            self.assertLess(time.monotonic() - started, 1)
        lock.close()

    def test_profile_and_period_boundary_counts(self):
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
        return Runtime(replace(self.settings, budgets=budgets or Budgets()), ScriptedModel(actions))

    def test_fake_profile_switch_and_isolation(self):
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

    def test_repair_and_invalidated_observation(self):
        result = self.scripted([{"action": "query", "sql": "DELETE FROM orders"}, QUERY, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        for bad in [{"action": "query", "sql": "SELECT * FROM private_truth"}, {"action": "oops"}]:
            result = self.scripted([QUERY, bad, ANSWER]).run(REQUEST)
            self.assertEqual(result["error"]["code"], "answer_validation_failed")
        result = self.scripted([QUERY, {"action": "answer", "answer_text": "3건"}, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")

    def test_model_retry_and_auth_no_fallback(self):
        result = self.scripted([{"raise_model": "model_request_failed", "transient": True}, QUERY, ANSWER]).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        for error in [{"raise_model": "model_auth_failed"},
                      {"raise_model": "model_request_failed", "transient": True, "retry_after": 2}]:
            result = self.scripted([error]).run(REQUEST)
            self.assertEqual(result["error"]["code"], error["raise_model"])

    def test_call_limits_and_final_call_success(self):
        result = self.scripted([QUERY, ANSWER], Budgets(max_model_calls=2)).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        result = self.scripted([QUERY], Budgets(max_model_calls=1)).run(REQUEST)
        self.assertEqual(result["error"]["code"], "turn_limit")
        result = self.scripted([{"action": "bad"}], Budgets(action_repair_attempts=0)).run(REQUEST)
        self.assertEqual(result["error"]["code"], "invalid_action")

    def test_uncooperative_model_deadlines(self):
        for budgets, expected in [(Budgets(model_timeout_seconds=1, model_transient_retries=0), "model_timeout"),
                                  (Budgets(request_timeout_seconds=1), "request_timeout")]:
            started = time.monotonic()
            result = self.scripted([{"sleep": 30}], budgets).run(REQUEST)
            self.assertEqual(result["error"]["code"], expected)
            self.assertLess(time.monotonic() - started, 3)

    def test_diagnostics_are_metadata_only(self):
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
