"""Protocol contract tests with binary streams and a mock parent process."""

from dataclasses import replace
import io
import json
import os
import queue
import subprocess
import sys
import threading
import unittest

from driftlens_sql_agent.runtime import Runtime
from driftlens_sql_agent.settings import Budgets, MAPPING
from driftlens_sql_agent.transport import MAX_LINE, serve, write_response
from test_core import DatabaseCase, REQUEST


def line(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class TransportTests(DatabaseCase):
    def run_stream(self, data, budgets=None, runtime=None):
        output, events = io.BytesIO(), []
        runtime = runtime or Runtime(replace(self.settings, budgets=budgets or Budgets()))
        code = serve(runtime, io.BytesIO(data), output, events.append)
        return code, [json.loads(row) for row in output.getvalue().splitlines()], events

    def test_framing_success_and_continuation(self):
        data = line(REQUEST) + b"\r\n" + line({**REQUEST, "request_id": "bad", "period": "x"})
        data += b"\n" + line({**REQUEST, "request_id": "last"})
        code, rows, events = self.run_stream(data)
        self.assertEqual(code, 0)
        self.assertEqual([r["request_id"] for r in rows], ["req-1", "bad", "last"])
        self.assertEqual([r["status"] for r in rows], ["ok", "error", "ok"])
        self.assertEqual(rows[1]["error"]["code"], "invalid_request")
        self.assertTrue(events)

    def test_protocol_errors_stop_without_echo(self):
        for raw in [b"\n", b"\xef\xbb\xbf" + line(REQUEST), b"\xff", b"{}", b"[]", b"null",
                    b'{"request_id":"SECRET","request_id":"x"}',
                    b'{"request_id":"x","request":NaN}', b'{"request_id":"bad id"}',
                    b"[" * 2000, b" " * (MAX_LINE + 1)]:
            with self.subTest(raw=raw[:60]):
                code, rows, events = self.run_stream(raw + b"\n" + line(REQUEST))
                self.assertEqual(code, 2)
                self.assertEqual(len(rows), 1)
                self.assertIsNone(rows[0]["request_id"])
                self.assertEqual(rows[0]["error"]["code"], "protocol_error")
                self.assertNotIn("SECRET", str(rows) + str(events))

    def test_exact_line_byte_limit(self):
        base = line(REQUEST)
        for ending in [b"", b"\n", b"\r\n"]:
            data = base + b" " * (MAX_LINE - len(base)) + ending
            self.assertEqual(self.run_stream(data)[0], 0)
            data = base + b" " * (MAX_LINE + 1 - len(base)) + ending
            self.assertEqual(self.run_stream(data)[1][0]["error"]["code"], "protocol_error")

    def test_duplicate_and_count_limit_reserve_invalid_ids(self):
        invalid = {**REQUEST, "period": "invalid"}
        code, rows, _ = self.run_stream(line(invalid) + b"\n" + line(REQUEST))
        self.assertEqual(code, 2)
        self.assertEqual(rows[-1]["error"]["code"], "duplicate_request_id")
        code, rows, _ = self.run_stream(line(invalid) + b"\n" + line({**REQUEST, "request_id": "next"}),
                                       Budgets(max_requests=1))
        self.assertEqual((code, rows[-1]["error"]["code"]), (2, "request_limit"))

    def test_internal_and_output_failures(self):
        class BrokenRuntime:
            settings = self.settings
            def run(self, *args, **kwargs):
                raise RuntimeError("SECRET")
        code, rows, events = self.run_stream(line(REQUEST), runtime=BrokenRuntime())
        self.assertEqual((code, rows), (1, []))
        self.assertNotIn("SECRET", str(events))

        class BrokenOutput(io.BytesIO):
            def write(self, data):
                raise OSError("SECRET")
        events = []
        code = serve(Runtime(self.settings), io.BytesIO(b"\n"), BrokenOutput(), events.append)
        self.assertEqual(code, 1)
        self.assertNotIn("SECRET", str(events))
        with self.assertRaises(RuntimeError):
            write_response(io.BytesIO(), {"huge": "x" * MAX_LINE})


class ProcessTests(DatabaseCase):
    def command(self, *, bad_schema=False):
        config = {"database": {"kind": "sqlite", "path": "orders.sqlite", "read_only": True},
                  "schema_mapping": MAPPING, "amount_unit": "integer_cents",
                  "model": {"provider": "fake", "id_env": "UPSTAGE_MODEL", "api_key_env": "UPSTAGE_API_KEY"}}
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (self.root / "profile.json").write_text(json.dumps(self.settings.profile.definition()), encoding="utf-8")
        return [sys.executable, "-m", "driftlens_sql_agent", "--config", str(self.root / "config.json"),
                "--profile", str(self.root / "profile.json")]

    def test_parent_observes_flush_before_stdin_eof(self):
        env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
        process = subprocess.Popen(self.command(), cwd=self.root, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.stdin.write(line(REQUEST) + b"\n")
            process.stdin.flush()
            received = queue.Queue()
            reader = threading.Thread(target=lambda: received.put(process.stdout.readline()), daemon=True)
            reader.start()
            result = json.loads(received.get(timeout=10))
            self.assertEqual(result["status"], "ok")
            self.assertIsNone(process.poll())  # Response delivered while input remains open.
            stdout, stderr = process.communicate(timeout=10)
            reader.join(timeout=1)
            self.assertEqual((process.returncode, stdout), (0, b""))
            self.assertNotIn(b"SELECT", stderr)
            self.assertNotIn(b"profile", stderr)
            self.assertTrue(all(isinstance(json.loads(row), dict) for row in stderr.splitlines()))
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def test_process_exit_codes_and_new_profile(self):
        command = self.command()
        result = subprocess.run(command, input=b"\n", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "protocol_error")
        for threshold, count in [(3000, 2), (2000, 5)]:
            profile = {**self.settings.profile.definition(), "threshold": threshold}
            (self.root / "profile.json").write_text(json.dumps(profile))
            result = subprocess.run(command, input=line(REQUEST), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["observation"]["reported_values"][0]["value"], count)
        (self.root / "profile.json").write_text("{}")
        result = subprocess.run(command, input=b"", capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (2, b""))


def mock_adapter(requests, responses, exit_code):
    """Test-only parent contract, never a real benchmark integration."""
    ids = [r.get("request_id") for r in responses]
    expected = [r["request_id"] for r in requests]
    if exit_code or ids != expected or len(ids) != len(set(ids)):
        raise ValueError("Failed session")
    public, failures = [], []
    for request, response in zip(requests, responses):
        if response["status"] == "error":
            failures.append(response)
        else:
            public.append({"log_id": request["request_id"], "timestamp": request["timestamp"],
                           "agent_id": "test", "team": "test", "request": request["request"],
                           **response["observation"]})
    return public, failures


class AdapterTests(DatabaseCase):
    def test_public_ten_fields_and_private_failures(self):
        requests = [REQUEST, {**REQUEST, "request_id": "no", "request": "삭제해"}]
        responses = [Runtime(self.settings).run(req) for req in requests]
        public, failures = mock_adapter(requests, responses, 0)
        self.assertEqual(set(public[0]), {"log_id", "timestamp", "agent_id", "team", "request", "sql",
                                         "answer_text", "definition_note", "reported_values", "referenced_concepts"})
        self.assertEqual(len(failures), 1)
        self.assertNotIn("error", public[0])
        for rows, code in [(responses[:1], 0), (responses * 2, 0), (responses, 1)]:
            with self.assertRaises(ValueError):
                mock_adapter(requests, rows, code)
