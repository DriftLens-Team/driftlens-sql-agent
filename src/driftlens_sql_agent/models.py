"""모델 호출을 별도 프로세스에 격리하고 응답 action을 검증한다."""

import json
import math
import os
import sys

from .errors import AgentError, ModelError
from .schemas import strict_json


class FakeModel:
    """Only three declared test questions; not a language-understanding model."""

    def generate(self, messages, *, timeout, max_bytes):
        """모델 교체 인터페이스: worker가 지정한 입력과 제한으로 다음 action을 반환한다."""
        # 오프라인 fixture 전용이다. 세 문장의 성공을 실제 언어 이해 품질로 간주하지 않는다.
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
    """spawn 프로세스 진입점: 모델 호출과 action 검사를 격리하고 안전한 결과만 보낸다."""
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")
    try:
        while True:
            messages, timeout = connection.recv()
            try:
                value = model.generate(messages, timeout=timeout, max_bytes=65536)
                # provider 문자열과 fake dict에 동일한 크기·키·타입 규칙을 적용한다.
                try:
                    text = value if type(value) is str else json.dumps(value, ensure_ascii=False, allow_nan=False)
                    if len(text.encode("utf-8")) > 65536:
                        raise ValueError
                    action = strict_json(text)
                    if type(action) is not dict:
                        raise ValueError
                    kind = action.get("action")
                    expected = {"query": {"action", "sql"}, "answer": {"action", "answer_text"},
                                "unsupported": {"action"}}
                    if type(kind) is not str or kind not in expected or set(action) != expected[kind]:
                        raise ValueError
                    if kind != "unsupported" and type(action["sql" if kind == "query" else "answer_text"]) is not str:
                        raise ValueError

                except (ValueError, TypeError, OverflowError, RecursionError):
                    raise AgentError("invalid_action") from None
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
