"""Loopback HTTP only: no real credentials or internet required."""

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import threading
import time
import unittest

from driftlens_sql_agent.errors import AgentError, ModelError
from driftlens_sql_agent.provider import UpstageModel
from driftlens_sql_agent.runtime import Runtime
from driftlens_sql_agent.settings import Budgets
from test_core import DatabaseCase, REQUEST, QUERY, ANSWER


def completion(action):
    """여러 HTTP 테스트에서 사용하는 실제 API 형태의 응답 봉투를 만든다."""
    return json.dumps({"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(action, ensure_ascii=False)}}]}).encode()


class HttpTests(DatabaseCase):
    def setUp(self):
        """unittest 준비 훅: 각 테스트가 독립된 데이터와 자원을 사용하게 한다."""
        super().setUp()
        self.responses, self.received = [], []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                """HTTP 서버 콜백: 테스트용 요청 로그가 결과 스트림을 오염시키지 않게 한다."""
                pass
            def do_POST(self):
                """HTTP 서버 콜백: 예약된 상태·본문·지연을 반환해 실제 어댑터를 검증한다."""
                owner.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                status, body, headers, slow = owner.responses.pop(0)
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    if slow:
                        for byte in body:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.1)
                    else:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        # unittest은 역순으로 정리한다. 서버 중단 → 소켓 닫기 → 스레드 회수를 보장한다.
        self.addCleanup(self.thread.join, timeout=2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.model = UpstageModel("test-model", "SECRET", f"http://127.0.0.1:{self.server.server_port}/chat")

    def response(self, status=200, body=None, headers=None, slow=False):
        """테스트에서 사용할 응답을 준비한다. 실제 네트워크 자격 증명은 사용하지 않는다."""
        self.responses.append((status, completion(QUERY) if body is None else body, headers or {}, slow))

    def test_http_success_and_generation_settings(self):
        """실제 HTTP 요청의 생성 옵션과 응답 해석을 확인한다."""
        self.response()
        # Upstage JSON 모드는 메시지에 JSON 지시가 없으면 실제 서버에서 400을 반환한다.
        prompt = files("driftlens_sql_agent").joinpath("prompts/system.txt").read_text(encoding="utf-8")
        action = self.model.generate([{"role": "system", "content": prompt}], timeout=2, max_bytes=65536)
        self.assertEqual(json.loads(action), QUERY)
        self.assertEqual(self.received[0]["temperature"], 0)
        self.assertFalse(self.received[0]["stream"])
        self.assertEqual(self.received[0]["response_format"], {"type": "json_object"})
        self.assertIn("json", self.received[0]["messages"][0]["content"].lower())
        self.assertNotIn("SECRET", repr(self.model))

    def test_http_classification(self):
        """HTTP 상태별 오류 코드·재시도 여부·인증값 비노출을 확인한다."""
        for status, code, transient in [(401, "model_auth_failed", False), (403, "model_auth_failed", False),
                                        (400, "model_request_failed", False), (408, "model_timeout", True),
                                        (429, "model_request_failed", True), (500, "model_request_failed", True),
                                        (503, "model_request_failed", True), (302, "model_request_failed", False)]:
            self.response(status, b"SECRET", {"Retry-After": "2", "Location": self.model.endpoint})
            with self.subTest(status=status), self.assertRaises(ModelError) as caught:
                self.model.generate([], timeout=2, max_bytes=65536)
            self.assertEqual((caught.exception.code, caught.exception.transient), (code, transient))
            self.assertEqual(caught.exception.retry_after if transient else 2, 2)
            self.assertNotIn("SECRET", str(caught.exception))

    def test_invalid_envelopes_and_size(self):
        """잘못된 응답 봉투와 과도한 응답 크기를 거부하는지 확인한다."""
        for body in [b"x", b"null", b'{"choices":[null]}', b'{"choices":[{"finish_reason":"stop","message":null}]}',
                     b"x" * 65537, completion(QUERY).replace(b'"stop"', b'"length"')]:
            self.response(body=body)
            with self.assertRaises(AgentError) as caught:
                self.model.generate([], timeout=2, max_bytes=65536)
            self.assertEqual(caught.exception.code, "invalid_action")

    def test_http_retry_in_runtime_and_slow_stream_deadline(self):
        """HTTP 재시도와 느린 응답의 전체 기한을 함께 검증한다."""
        self.response(429, b"rate limit")
        self.response(body=completion(QUERY))
        self.response(body=completion(ANSWER))
        result = Runtime(self.settings, self.model).run(REQUEST)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(self.received), 3)
        self.response(slow=True)
        started = time.monotonic()
        settings = replace(self.settings, budgets=Budgets(request_timeout_seconds=1))
        result = Runtime(settings, self.model).run(REQUEST)
        self.assertEqual(result["error"]["code"], "request_timeout")
        self.assertLess(time.monotonic() - started, 3)

    def test_connection_failure_and_retry_after(self):
        """연결 실패와 Retry-After의 숫자·날짜·비정상 값을 확인한다."""
        from unittest.mock import patch
        import urllib.error
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("SECRET")):
            with self.assertRaises(ModelError) as caught:
                self.model.generate([], timeout=1, max_bytes=65536)
        self.assertTrue(caught.exception.transient)
        self.assertNotIn("SECRET", str(caught.exception))
        # 헬퍼 구현 대신 실제 HTTP 오류에서 재시도 지연이 전달되는지 확인한다.
        for header, expected in [("NaN", 2), ("invalid", 2), ("-1", 0), ("0.5", 0.5),
                                 ("Wed, 21 Oct 2099 07:28:00 GMT", None)]:
            with self.subTest(header=header):
                self.response(429, b"rate limit", {"Retry-After": header})
                with self.assertRaises(ModelError) as caught:
                    self.model.generate([], timeout=2, max_bytes=65536)
                if expected is None:
                    self.assertGreater(caught.exception.retry_after, 1)
                else:
                    self.assertEqual(caught.exception.retry_after, expected)
