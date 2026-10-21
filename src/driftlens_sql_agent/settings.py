"""Startup-only, immutable settings. Secrets are never included in repr."""

from dataclasses import dataclass, field, fields
import os
from pathlib import Path
import re

from .errors import AgentError
from .schemas import strict_json


@dataclass(frozen=True)
class Budgets:
    max_model_calls: int = 5
    request_timeout_seconds: int = 60
    model_timeout_seconds: int = 20
    model_transient_retries: int = 1
    action_repair_attempts: int = 1
    sql_timeout_seconds: int = 2
    sql_vm_steps: int = 100000
    sql_max_chars: int = 10000
    sql_max_rows: int = 100
    max_requests: int = 10000

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            minimum = 0 if f.name in {"model_transient_retries", "action_repair_attempts"} else 1
            if type(value) is not int or not minimum <= value <= f.default:
                raise AgentError("invalid_config")


@dataclass(frozen=True)
class Profile:
    threshold: int

    def __post_init__(self):
        if type(self.threshold) is not int or self.threshold < 0:
            raise AgentError("invalid_config")

    def definition(self):
        return {"concept_id": "large_orders", "comparison": ">=",
                "threshold": self.threshold, "amount_unit": "integer_cents"}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    profile: Profile
    budgets: Budgets
    provider: str
    model_id: str | None = None
    api_key: str | None = field(default=None, repr=False)


MAPPING = {"table": "orders", "order_id": "order_id", "ordered_at": "ordered_at",
           "amount": "order_total_cents"}


def _keys(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError


def load_settings(config_path, profile_path, *, environ=None) -> Settings:
    env = os.environ if environ is None else environ
    try:
        path = Path(config_path).resolve()
        config = strict_json(path.read_text(encoding="utf-8"))
        profile = strict_json(Path(profile_path).read_text(encoding="utf-8"))
        _keys(config, {"database", "schema_mapping", "amount_unit", "model"}, {"budgets"})
        _keys(profile, {"concept_id", "comparison", "threshold", "amount_unit"})
        if (profile["concept_id"] != "large_orders" or profile["comparison"] != ">="
                or profile["amount_unit"] != "integer_cents" or config["amount_unit"] != "integer_cents"
                or config["schema_mapping"] != MAPPING):
            raise ValueError
        selected = Profile(profile["threshold"])
        database = config["database"]
        _keys(database, {"kind", "path", "read_only"})
        if (database["kind"] != "sqlite" or database["read_only"] is not True
                or type(database["path"]) is not str or not database["path"].strip()):
            raise ValueError
        db_path = (path.parent / database["path"]).resolve()
        if not db_path.is_file():
            raise ValueError
        model = config["model"]
        _keys(model, {"provider", "id_env", "api_key_env"})
        if model["provider"] not in {"fake", "upstage"}:
            raise ValueError
        for key in ("id_env", "api_key_env"):
            if type(model[key]) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", model[key]):
                raise ValueError
        budget_values = config.get("budgets", {})
        _keys(budget_values, set(), {f.name for f in fields(Budgets)})
        model_id = env.get(model["id_env"]) if model["provider"] == "upstage" else None
        api_key = env.get(model["api_key_env"]) if model["provider"] == "upstage" else None
        if model["provider"] == "upstage" and (not model_id or not model_id.strip() or not api_key or not api_key.strip()):
            raise ValueError
        return Settings(db_path, selected, Budgets(**budget_values), model["provider"], model_id, api_key)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise AgentError("invalid_config") from None
