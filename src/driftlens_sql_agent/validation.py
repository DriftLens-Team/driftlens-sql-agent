"""Action and observation-grounded answer validation."""

import json
import re

from .errors import AgentError
from .schemas import strict_json


def action_value(value):
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
        return action
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise AgentError("invalid_action") from None


def count_value(result):
    rows = result["rows"]
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
        raise AgentError("sql_error")
    return rows[0][0]


def answer_value(text, value):
    # Small, explicit answer grammar prevents extra definitions or hidden commentary.
    if type(text) is not str or not re.fullmatch(
        rf"(?:이번 주 |해당 주의 |주간 )?대형 주문(?:은 | 수는 | 건수는 ){value}건입니다\.", text
    ):
        raise AgentError("answer_validation_failed")
    return text
