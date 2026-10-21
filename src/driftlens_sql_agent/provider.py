"""Upstage Chat Completions adapter; runtime owns retries and total deadlines."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import http.client
import json
import math
import socket
import urllib.error
import urllib.request

from .errors import AgentError, ModelError
from .schemas import strict_json


ENDPOINT = "https://api.upstage.ai/v1/chat/completions"
GENERATION = {"temperature": 0, "max_tokens": 1024, "stream": False,
              "response_format": {"type": "json_object"}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """urllib 콜백: 인증 헤더가 다른 주소로 전달되지 않도록 리다이렉트를 거부한다."""
        return None


@dataclass(frozen=True)
class UpstageModel:
    model_id: str
    api_key: str = field(repr=False)
    # Test injection only. Runtime config cannot redirect credentials to another host.
    endpoint: str = ENDPOINT

    def generate(self, messages, *, timeout, max_bytes):
        """모델 교체 인터페이스: worker가 지정한 입력과 제한으로 다음 action을 반환한다."""
        payload = json.dumps({"model": self.model_id, "messages": messages, **GENERATION},
                             ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=payload, headers={
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json", "Accept": "application/json",
        }, method="POST")
        try:
            # No provider retries and no credential-bearing redirects.
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                raw = response.read(max_bytes + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            # 단 한 곳에서 쓰는 Retry-After 해석은 HTTP 오류 처리 안에서 수행한다.
            value = error.headers.get("Retry-After")
            delay = 0
            if value is not None:
                try:
                    delay = float(value)
                except ValueError:
                    try:
                        stamp = parsedate_to_datetime(value)
                        delay = (stamp - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 2
                delay = max(0, delay) if math.isfinite(delay) else 2
            error.close()
            if status in {401, 403}:
                raise ModelError("model_auth_failed") from None
            if status == 408:
                raise ModelError("model_timeout", transient=True, retry_after=delay) from None
            raise ModelError("model_request_failed", transient=status == 429 or 500 <= status <= 599,
                             retry_after=delay) from None
        except (TimeoutError, socket.timeout):
            raise ModelError("model_timeout", transient=True) from None
        except urllib.error.URLError as error:
            code = "model_timeout" if isinstance(error.reason, TimeoutError) else "model_request_failed"
            raise ModelError(code, transient=True) from None
        except (OSError, http.client.HTTPException):
            raise ModelError("model_request_failed", transient=True) from None
        try:
            if len(raw) > max_bytes:
                raise ValueError
            body = strict_json(raw.decode("utf-8"))
            if type(body) is not dict:
                raise ValueError
            choice = body["choices"]
            if (type(choice) is not list or len(choice) != 1 or type(choice[0]) is not dict
                    or choice[0]["finish_reason"] != "stop"):
                raise ValueError
            message = choice[0]["message"]
            if type(message) is not dict or message.get("role") != "assistant" or message.get("tool_calls"):
                raise ValueError
            content = message["content"]
            if type(content) is not str:
                raise ValueError
            return content
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            raise AgentError("invalid_action") from None
