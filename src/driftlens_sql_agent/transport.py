"""Bounded UTF-8 JSONL over binary streams; sequential and immediately flushed."""

import json

from .errors import AgentError
from .schemas import Request, strict_json


MAX_LINE = 65536


def error_response(request_id, code):
    """프로토콜 오류 세 경로에서 동일한 응답 형식을 사용한다."""
    return {"request_id": request_id, "status": "error", "error": AgentError(code).record()}


def write_response(stream, response):
    """한 응답의 UTF-8 바이트 수와 완전한 쓰기를 확인한 뒤 즉시 flush한다."""
    data = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_LINE:
        raise RuntimeError("Output exceeds protocol limit")
    written = stream.write(data + b"\n")
    if written != len(data) + 1:
        raise OSError("Incomplete protocol write")
    stream.flush()


def serve(runtime, input_stream, output_stream, diagnostic):
    """입력 프레이밍과 ID 중복을 검사하고 요청을 순서대로 실행한다."""
    seen = set()
    try:
        while True:
            raw = input_stream.readline(MAX_LINE + 3)
            if not raw:
                return 0
            if raw.endswith(b"\n"):
                raw = raw[:-1]
                if raw.endswith(b"\r"):
                    raw = raw[:-1]
            try:
                if len(raw) > MAX_LINE or not raw or raw.startswith(b"\xef\xbb\xbf"):
                    raise ValueError
                obj = strict_json(raw.decode("utf-8"))
                try:
                    if getattr(runtime.settings, "protocol", "v1") == "v2":
                        from .semalign import SemAlignRequest
                        SemAlignRequest.parse(obj)
                    else:
                        Request.parse(obj)
                except AgentError as error:
                    if error.code == "protocol_error":
                        raise ValueError from None
                    # Valid IDs are reserved even when the remaining fields are invalid.
                request_id = obj["request_id"]
            except (ValueError, TypeError, KeyError, RecursionError):
                write_response(output_stream, error_response(None, "protocol_error"))
                diagnostic({"stage": "protocol_finished", "code": "protocol_error"})
                return 2
            fatal = "duplicate_request_id" if request_id in seen else (
                "request_limit" if len(seen) >= runtime.settings.budgets.max_requests else None)
            if fatal:
                write_response(output_stream, error_response(request_id, fatal))
                diagnostic({"request_id": request_id, "stage": "protocol_finished", "code": fatal})
                return 2
            seen.add(request_id)
            try:
                response = runtime.run(obj, diagnostic=diagnostic)
            except AgentError as error:
                if error.code != "invalid_request":
                    raise
                response = error_response(request_id, "invalid_request")
                diagnostic({"request_id": request_id, "stage": "request_finished", "code": error.code})
            write_response(output_stream, response)
    except Exception:
        # Never include input, output, paths, HTTP bodies or exception strings.
        try:
            diagnostic({"stage": "process_finished", "code": "internal_error"})
        except Exception:
            pass
        return 1
