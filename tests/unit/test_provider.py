"""Loopback HTTP only: no real credentials or internet required."""

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest

from driftlens_sql_agent.errors import AgentError, ModelError
from driftlens_sql_agent.provider import UpstageModel, retry_delay
from driftlens_sql_agent.runtime import Runtime
from driftlens_sql_agent.settings import Budgets
from test_core import DatabaseCase, REQUEST, QUERY, ANSWER


def completion(action):
    return json.dumps({"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(action, ensure_ascii=False)}}]}).encode()


class HttpTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.responses, self.received = [], []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
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
        self.addCleanup(self.cleanup_server)
        self.model = UpstageModel("test-model", "SECRET", f"http://127.0.0.1:{self.server.server_port}/chat")

    def cleanup_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def response(self, status=200, body=None, headers=None, slow=False):
        self.responses.append((status, completion(QUERY) if body is None else body, headers or {}, slow))

    def test_http_success_and_generation_settings(self):
        self.response()
        action = self.model.generate([{"role": "user", "content": "질문"}], timeout=2, max_bytes=65536)
        self.assertEqual(json.loads(action), QUERY)
        self.assertEqual(self.received[0]["temperature"], 0)
        self.assertFalse(self.received[0]["stream"])
        self.assertNotIn("SECRET", repr(self.model))

    def test_http_classification(self):
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
        for body in [b"x", b"null", b'{"choices":[null]}', b'{"choices":[{"finish_reason":"stop","message":null}]}',
                     b"x" * 65537, completion(QUERY).replace(b'"stop"', b'"length"')]:
            self.response(body=body)
            with self.assertRaises(AgentError) as caught:
                self.model.generate([], timeout=2, max_bytes=65536)
            self.assertEqual(caught.exception.code, "invalid_action")

    def test_http_retry_in_runtime_and_slow_stream_deadline(self):
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
        from unittest.mock import patch
        import urllib.error
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("SECRET")):
            with self.assertRaises(ModelError) as caught:
                self.model.generate([], timeout=1, max_bytes=65536)
        self.assertTrue(caught.exception.transient)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(retry_delay("NaN"), 2)
        self.assertEqual(retry_delay("invalid"), 2)
        self.assertGreater(retry_delay("Wed, 21 Oct 2099 07:28:00 GMT"), 1)
