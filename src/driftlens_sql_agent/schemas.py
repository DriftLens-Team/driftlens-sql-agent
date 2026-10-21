"""Strict JSON and request values; stream framing belongs to transport."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import math
import re

from .errors import AgentError


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("nonfinite number")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite number")
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject, parse_float=number)


@dataclass(frozen=True)
class Request:
    request_id: str
    question: str
    period: str
    start: date
    end: date
    assumed_utc: bool

    @classmethod
    def parse(cls, obj):
        if (type(obj) is not dict or type(obj.get("request_id")) is not str
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", obj["request_id"])):
            raise AgentError("protocol_error")
        try:
            if set(obj) != {"request_id", "request", "timestamp", "period"}:
                raise ValueError
            question = obj["request"]
            if type(question) is not str or not question.strip() or len(question) > 4096:
                raise ValueError
            question.encode("utf-8")
            if type(obj["period"]) is not str or not re.fullmatch(r"\d{4}-W\d{2}", obj["period"]):
                raise ValueError
            year, week = obj["period"].split("-W")
            start = date.fromisocalendar(int(year), int(week), 1)
            end = start + timedelta(days=7)
            stamp = obj["timestamp"]
            if type(stamp) is not str or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?", stamp
            ):
                raise ValueError
            parsed = datetime.fromisoformat(stamp)
            assumed = parsed.tzinfo is None
            parsed = parsed.replace(tzinfo=timezone.utc) if assumed else parsed.astimezone(timezone.utc)
            expected = datetime.combine(end, datetime.min.time(), timezone.utc) - timedelta(seconds=1)
            if parsed != expected:
                raise ValueError
            return cls(obj["request_id"], question, obj["period"], start, end, assumed)
        except (ValueError, TypeError, OverflowError):
            raise AgentError("invalid_request") from None
