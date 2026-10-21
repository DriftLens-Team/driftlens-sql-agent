"""Bounded per-request loop independent of stream framing and provider HTTP."""

from importlib.resources import files
import json
import time

from .errors import AgentError, ModelError
from .models import FakeModel, ModelSession
from .provider import UpstageModel
from .schemas import Request
from .settings import Settings
from .sql_access import query, validate_database
from .validation import answer_value, count_value


class Runtime:
    def __init__(self, settings: Settings, model=None):
        validate_database(settings.db_path)
        self.settings = settings
        if model is None:
            model = FakeModel() if settings.provider == "fake" else UpstageModel(settings.model_id, settings.api_key)
        self.model = model

    def run(self, obj, *, diagnostic=None):
        request = Request.parse(obj)
        started = time.monotonic()
        budgets = self.settings.budgets
        deadline = started + budgets.request_timeout_seconds

        def emit(stage, code=None):
            if diagnostic is not None:
                event = {"request_id": request.request_id, "stage": stage,
                         "elapsed_ms": round((time.monotonic() - started) * 1000)}
                if code is not None:
                    event["code"] = code
                diagnostic(event)

        emit("request_started")
        if request.assumed_utc:
            emit("timestamp_assumed_utc")
        context = {"question": request.question, "period": request.period,
                   "start": str(request.start), "end": str(request.end),
                   "definition": self.settings.profile.definition()}
        messages = [
            {"role": "system", "content": files("driftlens_sql_agent").joinpath("prompts/system.txt").read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        calls = repairs = retries = 0
        observation = None
        session = ModelSession(self.model)

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise AgentError("request_timeout")
            return seconds

        def may_retry(error):
            remaining()
            if calls >= budgets.max_model_calls:
                raise AgentError("turn_limit")

        try:
            while True:
                remaining()
                if calls >= budgets.max_model_calls:
                    raise AgentError("turn_limit")
                calls += 1
                emit("model_call")
                try:
                    action = session.call(messages, timeout=min(remaining(), budgets.model_timeout_seconds))
                except ModelError as error:
                    remaining()
                    if not error.transient:
                        raise
                    may_retry(error)
                    if error.retry_after > 1:
                        raise AgentError("model_request_failed") from None
                    if retries >= budgets.model_transient_retries:
                        raise
                    retries += 1
                    emit("model_retry", error.code)
                    time.sleep(min(error.retry_after, remaining()))
                    continue
                except AgentError as error:
                    if error.code != "invalid_action":
                        raise
                    observation = None
                    may_retry(error)
                    if repairs >= budgets.action_repair_attempts:
                        raise
                    repairs += 1
                    messages.append({"role": "user", "content": "ACTION_ERROR:" + json.dumps(error.record())})
                    emit("action_repair", error.code)
                    continue

                remaining()
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                kind = action["action"]
                if kind == "unsupported":
                    raise AgentError("unsupported_request")
                try:
                    if kind == "query":
                        observation = None
                        result = query(self.settings.db_path, action["sql"], budgets, deadline=deadline)
                        value = count_value(result)
                        observation = {"sql": action["sql"], "value": value}
                        messages.append({"role": "user", "content": "SQL_RESULT:" + json.dumps({"value": value})})
                        emit("sql_succeeded")
                    else:
                        if observation is None:
                            raise AgentError("answer_validation_failed")
                        answer = answer_value(action["answer_text"], observation["value"])
                        output = {"sql": observation["sql"], "answer_text": answer,
                                  "definition_note": f"주문 총액 {self.settings.profile.threshold}센트 이상인 주문",
                                  "reported_values": [{"concept_id": "large_orders", "value": observation["value"], "period": request.period}],
                                  "referenced_concepts": ["large_orders"]}
                        remaining()
                        emit("request_finished", "ok")
                        return {"request_id": request.request_id, "status": "ok", "observation": output}
                except AgentError as error:
                    if error.code not in {"sql_error", "answer_validation_failed"}:
                        raise
                    may_retry(error)
                    if repairs >= budgets.action_repair_attempts:
                        raise
                    repairs += 1
                    messages.append({"role": "user", "content": "ACTION_ERROR:" + json.dumps(error.record())})
                    emit("action_repair", error.code)
        except AgentError as error:
            emit("request_finished", error.code)
            return {"request_id": request.request_id, "status": "error", "error": error.record()}
        finally:
            session.close()
