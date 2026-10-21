"""Action and observation-grounded answer validation."""

import re

from .errors import AgentError


def count_value(result):
    """관측값을 음수가 아닌 단일 정수로 제한하고 bool도 거부한다."""
    rows = result["rows"]
    if len(rows) != 1 or len(rows[0]) != 1 or type(rows[0][0]) is not int or rows[0][0] < 0:
        raise AgentError("sql_error")
    return rows[0][0]


def answer_value(text, value):
    # Small, explicit answer grammar prevents extra definitions or hidden commentary.
    """답변이 최신 관측 건수만 설명하는 허용 문장인지 검사한다."""
    if type(text) is not str or not re.fullmatch(
        rf"(?:이번 주 |해당 주의 |주간 )?대형 주문(?:은 | 수는 | 건수는 ){value}건입니다\.", text
    ):
        raise AgentError("answer_validation_failed")
    return text
