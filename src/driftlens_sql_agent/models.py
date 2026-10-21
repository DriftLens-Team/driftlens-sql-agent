"""Model boundary and deterministic offline double; no live provider yet."""

import json
import math
import multiprocessing
import os
import sys
import time
from typing import Protocol

from .errors import AgentError, ModelError
from .validation import action_value


class Model(Protocol):
    def generate(self, messages: list[dict], *, timeout: float, max_bytes: int): ...


class FakeModel:
    """Only three declared test questions; not a language-understanding model."""

    def generate(self, messages, *, timeout, max_bytes):
        context = json.loads(messages[1]["content"])
        if context["question"] not in {
            "이번 주 대형 주문은 몇 건인가요?", "해당 주의 대형 주문 수를 알려주세요.",
            "주간 대형 주문 건수를 조회해 주세요.",
        }:
            return {"action": "unsupported"}
        if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("SQL_RESULT:"):
            result = json.loads(messages[-1]["content"][11:])
            if "value" in result:
                return {"action": "answer", "answer_text": f"이번 주 대형 주문은 {result['value']}건입니다."}
        sql = ("SELECT COUNT(*) FROM orders WHERE ordered_at >= "
               f"'{context['start']}' AND ordered_at < '{context['end']}' "
               f"AND order_total_cents >= {context['definition']['threshold']}")
        return {"action": "query", "sql": sql}


def _worker(connection, model):
    # Provider libraries must not write into the host's future JSONL stream.
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")
    try:
        while True:
            messages, timeout = connection.recv()
            try:
                action = action_value(model.generate(messages, timeout=timeout, max_bytes=65536))
                payload = {"action": action}
            except ModelError as error:
                delay = error.retry_after
                if type(delay) not in (int, float) or not math.isfinite(delay) or delay < 0:
                    delay = 2
                payload = {"error": error.code, "transient": error.transient, "retry_after": delay}
            except AgentError as error:
                payload = {"error": error.code}
            except Exception:
                payload = {"internal_error": True}
            connection.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class ModelSession:
    """One isolated model instance per request; timeout terminates its worker."""

    def __init__(self, model: Model):
        self.model = model
        self.process = None
        self.connection = None

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=0.5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=0.5)
            self.process.close()
            self.process = None

    def call(self, messages, *, timeout):
        expires = time.monotonic() + timeout
        if self.process is None:
            context = multiprocessing.get_context("spawn")
            self.connection, child = context.Pipe()
            self.process = context.Process(target=_worker, args=(child, self.model), daemon=True)
            self.process.start()
            child.close()
        try:
            self.connection.send((messages, max(0, expires - time.monotonic())))
            if not self.connection.poll(max(0, expires - time.monotonic())):
                self.close()
                raise ModelError("model_timeout", transient=True)
            result = json.loads(self.connection.recv_bytes(maxlength=70000))
        except (EOFError, OSError):
            self.close()
            raise RuntimeError("Model worker failed") from None
        if time.monotonic() >= expires:
            self.close()
            raise ModelError("model_timeout", transient=True)
        if result.get("internal_error"):
            raise RuntimeError("Model worker failed")
        if "error" in result:
            if result["error"].startswith("model_"):
                raise ModelError(result["error"], transient=result.get("transient", False),
                                 retry_after=result.get("retry_after", 0))
            raise AgentError(result["error"])
        return result["action"]
