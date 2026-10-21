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
    """여러 프로토콜 테스트의 입력을 UTF-8 JSON 바이트로 만든다."""
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class TransportTests(DatabaseCase):
    def run_stream(self, data, budgets=None, runtime=None):
        """여러 프레이밍 사례를 메모리 스트림에 넣고 출력·진단을 분리해 수집한다."""
        output, events = io.BytesIO(), []
        runtime = runtime or Runtime(replace(self.settings, budgets=budgets or Budgets()))
        code = serve(runtime, io.BytesIO(data), output, events.append)
        return code, [json.loads(row) for row in output.getvalue().splitlines()], events

    def test_framing_success_and_continuation(self):
        """CRLF·마지막 줄·업무 오류 뒤 후속 요청 처리 여부를 확인한다."""
        data = line(REQUEST) + b"\r\n" + line({**REQUEST, "request_id": "bad", "period": "x"})
        data += b"\n" + line({**REQUEST, "request_id": "last"})
        code, rows, events = self.run_stream(data)
        self.assertEqual(code, 0)
        self.assertEqual([r["request_id"] for r in rows], ["req-1", "bad", "last"])
        self.assertEqual([r["status"] for r in rows], ["ok", "error", "ok"])
        self.assertEqual(rows[1]["error"]["code"], "invalid_request")
        self.assertTrue(events)

    def test_protocol_errors_stop_without_echo(self):
        """잘못된 인코딩·JSON·ID·크기에서 입력을 노출하지 않고 종료하는지 확인한다."""
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
        """구분자 형태와 관계없이 정확한 바이트 상한을 적용하는지 확인한다."""
        base = line(REQUEST)
        for ending in [b"", b"\n", b"\r\n"]:
            data = base + b" " * (MAX_LINE - len(base)) + ending
            self.assertEqual(self.run_stream(data)[0], 0)
            data = base + b" " * (MAX_LINE + 1 - len(base)) + ending
            self.assertEqual(self.run_stream(data)[1][0]["error"]["code"], "protocol_error")

    def test_duplicate_and_count_limit_reserve_invalid_ids(self):
        """업무 오류 요청의 ID도 예약하고 중복·요청 수 초과를 차단하는지 확인한다."""
        invalid = {**REQUEST, "period": "invalid"}
        code, rows, _ = self.run_stream(line(invalid) + b"\n" + line(REQUEST))
        self.assertEqual(code, 2)
        self.assertEqual(rows[-1]["error"]["code"], "duplicate_request_id")
        code, rows, _ = self.run_stream(line(invalid) + b"\n" + line({**REQUEST, "request_id": "next"}),
                                       Budgets(max_requests=1))
        self.assertEqual((code, rows[-1]["error"]["code"]), (2, "request_limit"))

    def test_internal_and_output_failures(self):
        """내부 예외와 출력 실패에서 비밀값을 노출하지 않는지 확인한다."""
        class BrokenRuntime:
            settings = self.settings
            def run(self, *args, **kwargs):
                """runtime 교체 인터페이스: 내부 결함을 주입해 예외 원문 비노출을 확인한다."""
                raise RuntimeError("SECRET")
        code, rows, events = self.run_stream(line(REQUEST), runtime=BrokenRuntime())
        self.assertEqual((code, rows), (1, []))
        self.assertNotIn("SECRET", str(events))

        class BrokenOutput(io.BytesIO):
            def write(self, data):
                """출력 스트림 콜백: 쓰기 실패가 내부 오류로 처리되는지 재현한다."""
                raise OSError("SECRET")
        events = []
        code = serve(Runtime(self.settings), io.BytesIO(b"\n"), BrokenOutput(), events.append)
        self.assertEqual(code, 1)
        self.assertNotIn("SECRET", str(events))
        with self.assertRaises(RuntimeError):
            write_response(io.BytesIO(), {"huge": "x" * MAX_LINE})


class ProcessTests(DatabaseCase):
    def setUp(self):
        """unittest 준비 훅: 각 테스트가 독립된 데이터와 자원을 사용하게 한다."""
        super().setUp()
        config = {"database": {"kind": "sqlite", "path": "orders.sqlite", "read_only": True},
                  "schema_mapping": MAPPING, "amount_unit": "integer_cents",
                  "model": {"provider": "fake", "id_env": "UPSTAGE_MODEL", "api_key_env": "UPSTAGE_API_KEY"}}
        (self.root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (self.root / "profile.json").write_text(json.dumps(self.settings.profile.definition()), encoding="utf-8")
        self.command = [sys.executable, "-m", "driftlens_sql_agent", "--config", str(self.root / "config.json"),
                "--profile", str(self.root / "profile.json")]

    def test_parent_observes_flush_before_stdin_eof(self):
        """입력 종료를 기다리지 않고 부모가 응답을 받을 수 있는지 확인한다."""
        env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
        process = subprocess.Popen(self.command, cwd=self.root, env=env, stdin=subprocess.PIPE,
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
        """프로세스 종료 코드와 새 profile의 실행 반영을 확인한다."""
        command = self.command
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


class AdapterTests(DatabaseCase):
    def test_public_ten_fields_and_private_failures(self):
        """모의 부모에서 공개 로그 10개 필드와 실패 응답의 분리를 확인한다."""
        requests = [REQUEST, {**REQUEST, "request_id": "no", "request": "삭제해"}]
        responses = [Runtime(self.settings).run(req) for req in requests]
        for rows, exit_code, valid in [(responses, 0, True), (responses[:1], 0, False),
                                       (responses * 2, 0, False), (responses, 1, False)]:
            # 실제 benchmark 대신 부모 프로세스의 ID 대응·종료 코드 계약만 확인한다.
            ids = [r.get("request_id") for r in rows]
            expected = [r["request_id"] for r in requests]
            if exit_code or ids != expected or len(ids) != len(set(ids)):
                self.assertFalse(valid)
                continue
            public, failures = [], []
            for request, response in zip(requests, rows):
                if response["status"] == "error":
                    failures.append(response)
                else:
                    public.append({"log_id": request["request_id"], "timestamp": request["timestamp"],
                                   "agent_id": "test", "team": "test", "request": request["request"],
                                   **response["observation"]})
            self.assertTrue(valid)
            self.assertEqual(set(public[0]), {"log_id", "timestamp", "agent_id", "team", "request", "sql",
                                             "answer_text", "definition_note", "reported_values", "referenced_concepts"})
            self.assertEqual(len(failures), 1)
            self.assertNotIn("error", public[0])
