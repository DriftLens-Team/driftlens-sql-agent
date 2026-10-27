"""Opt-in SemAlign values, profiles and a strictly weekly v2 request boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import re

from .errors import AgentError
from .settings import Budgets

UNITS = {
    "sa_food_orders": "count", "sa_drink_orders": "count",
    "sa_customers_active": "count", "sa_customers_new": "count",
    "sa_order_value_avg": "cents", "sa_revenue_growth_wow": "ratio", "sa_tax_rate_avg": "ratio",
}
SLOTS = {"grain", "aggregation", "population", "measure", "conditions", "time_semantics", "null_policy", "unit"}
TABLES = {
    "orders": {"order_id", "customer_id", "ordered_at", "location_id", "subtotal_cents", "tax_paid_cents", "order_total_cents"},
    "order_items": {"order_item_id", "order_id", "product_id"},
    "products": {"product_id", "product_name", "product_type", "product_price_cents", "product_description"},
    "locations": {"location_id", "location_name", "opened_at", "tax_rate"},
}


@dataclass(frozen=True)
class SemAlignBudgets(Budgets):
    """Explicit v2 limits cover historical aggregates while keeping finite budgets."""
    sql_vm_steps: int = 20_000_000
    sql_timeout_seconds: int = 5


@dataclass(frozen=True)
class SemAlignProfile:
    """One current definition, with no version, schedule, truth or oracle fields."""
    concept_id: str
    label: str
    definition: str
    unit: str
    semantics: dict

    def __post_init__(self):
        """Dataclass hook validates the only definition visible to this process."""
        if (self.concept_id not in UNITS or self.unit != UNITS[self.concept_id]
                or any(type(v) is not str or not v.strip() or len(v) > 4096 for v in (self.label, self.definition))
                or type(self.semantics) is not dict or set(self.semantics) != SLOTS
                or any(type(v) is not str or not v.strip() or len(v) > 256 for v in self.semantics.values())
                or self.semantics["unit"] != self.unit):
            raise AgentError("invalid_config")


@dataclass(frozen=True)
class SemAlignRequest:
    request_id: str
    question: str
    concept_id: str
    start: str
    end: str
    window: dict
    as_of: str
    assumed_utc: bool = False

    @classmethod
    def parse(cls, obj):
        """Protocol parser shared by framing, runtime and contract validation tests."""
        if (type(obj) is not dict or type(obj.get("request_id")) is not str
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", obj["request_id"])):
            raise AgentError("protocol_error")
        try:
            if set(obj) != {"request_id", "request", "timestamp", "concept_id", "window", "as_of"}:
                raise ValueError
            question = obj["request"]
            if type(question) is not str or not question.strip() or len(question) > 4096:
                raise ValueError
            question.encode("utf-8")
            if type(obj["concept_id"]) is not str or obj["concept_id"] not in UNITS:
                raise ValueError
            window = obj["window"]
            if type(window) is not dict or set(window) != {"start", "end"}:
                raise ValueError
            stamps = [window["start"], window["end"], obj["as_of"], obj["timestamp"]]
            if any(type(s) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s) for s in stamps):
                raise ValueError
            start, end, cutoff, question_at = map(datetime.fromisoformat, stamps)
            if (start.weekday() != 0 or start.time() != datetime.min.time()
                    or end - start != timedelta(days=7) or cutoff != end or question_at < end):
                raise ValueError
            # DB timestamps have no UTC suffix. Date-only bounds compare correctly
            # with both date and YYYY-MM-DDTHH:MM:SS values at midnight boundaries.
            return cls(obj["request_id"], question, obj["concept_id"], window["start"][:10],
                       window["end"][:10], dict(window), obj["as_of"])
        except (KeyError, ValueError, TypeError, OverflowError):
            raise AgentError("invalid_request") from None


def metric_value(result, unit):
    """Apply the source reporting rule without converting query failures into null."""
    rows = result["rows"]
    if len(rows) != 1 or len(rows[0]) != 1:
        raise AgentError("sql_error")
    value = rows[0][0]
    if value is None:
        return None  # Eligibility and null's semantic cause belong to private validation.
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AgentError("sql_error")
    if unit == "count":
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise AgentError("sql_error")
    elif unit == "cents":
        value = round(value)
    elif unit == "ratio":
        value = round(value, 4)
    else:
        raise AgentError("sql_error")
    return value


def metric_answer(text, value, unit):
    """Restrict v2 answers to one observed value and its declared unit, or null."""
    expected = "계산할 수 없습니다." if value is None else f"결과는 {value} {unit}입니다."
    if type(text) is not str or text != expected:
        raise AgentError("answer_validation_failed")
    return text
