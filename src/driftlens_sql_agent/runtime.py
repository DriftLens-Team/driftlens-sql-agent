"""Bounded per-request loop independent of stream framing and provider HTTP."""

from importlib.resources import files
from decimal import Decimal
from dataclasses import asdict
from datetime import date, timedelta
import json
import multiprocessing
import re
import time
import unicodedata

from .errors import AgentError, ModelError
from .models import FakeModel, _worker
from .provider import UpstageModel
from .schemas import Request
from .settings import Settings
from .sql_access import query, validate_database
from .validation import answer_value, count_value
from .semalign import SemAlignRequest, TABLES, metric_answer, metric_value
from .semalign_fake import FakeSemAlignModel


class Runtime:
    def __init__(self, settings: Settings, model=None):
        """생성자 훅: 이 인스턴스의 실행 상태와 검증된 의존성을 준비한다."""
        validate_database(settings.db_path, protocol=settings.protocol)
        self.settings = settings
        if model is None:
            if settings.provider == "fake":
                model = FakeSemAlignModel() if settings.protocol == "v2" else FakeModel()
            else:
                model = UpstageModel(settings.model_id, settings.api_key)
        self.model = model

    def run(self, obj, *, diagnostic=None):
        """요청마다 상태를 새로 만들고 모델 → SQL → 답변을 제한된 횟수 안에서 실행한다."""
        v2 = self.settings.protocol == "v2"
        request = SemAlignRequest.parse(obj) if v2 else Request.parse(obj)
        if v2 and request.concept_id != self.settings.profile.concept_id:
            raise AgentError("invalid_request")
        started = time.monotonic()
        budgets = self.settings.budgets
        deadline = started + budgets.request_timeout_seconds

        def emit(stage, code=None):
            """여러 실행 단계의 진단을 같은 필드로 남기고 입력·SQL·비밀값은 제외한다."""
            if diagnostic is not None:
                event = {"request_id": request.request_id, "stage": stage,
                         "elapsed_ms": round((time.monotonic() - started) * 1000)}
                if code is not None:
                    event["code"] = code
                diagnostic(event)

        emit("request_started")
        if request.assumed_utc:
            emit("timestamp_assumed_utc")
        # 명시된 센트 금액의 충돌은 모델 판단에 맡기지 않는다. 원문은 변경하지 않고
        # 비교용 텍스트만 정규화한다. 질문에 숫자가 있다는 이유만으로 주차 등을 거부하지 않는다.
        normalized_question = unicodedata.normalize("NFKC", request.question)
        amounts = re.findall(
            r"(?<![0-9.,+-])([+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*(?:센트|cents?\b)",
            normalized_question, re.IGNORECASE,
        )
        if not v2 and any(Decimal(amount.replace(",", "")) != self.settings.profile.threshold for amount in amounts):
            # 조회 이전에 종료하므로 모델이 기존 정의로 질문을 바꿔 답할 수 없다.
            emit("request_finished", "unsupported_request")
            return {"request_id": request.request_id, "status": "error",
                    "error": AgentError("unsupported_request").record()}
        if v2:
            allowed = {"orders"}
            if request.concept_id in {"sa_food_orders", "sa_drink_orders"}:
                allowed |= {"order_items", "products"}
            # Bind values come only from the validated request, never from model SQL.
            # They omit the UTC suffix because the source stores naive UTC strings.
            sql_parameters = {"week_start": request.start, "week_end": request.end,
                              "previous_start": str(date.fromisoformat(request.start) - timedelta(days=7))}
            # Completeness compares timestamps, not a shorter date prefix: an
            # order exactly at prior midnight must count as available history.
            sql_parameters["history_start"] = sql_parameters["previous_start"] + "T00:00:00"
            context = {"question": request.question, "concept_id": request.concept_id,
                       "start": request.start, "end": request.end, "as_of": request.as_of,
                       "sql_parameters": sql_parameters,
                       "definition": asdict(self.settings.profile),
                       "schema": {t: sorted(TABLES[t]) for t in sorted(allowed)}}
        else:
            context = {"question": request.question, "period": request.period,
                       "start": str(request.start), "end": str(request.end),
                       "definition": self.settings.profile.definition()}
        prompt = "semalign.txt" if v2 else "system.txt"
        messages = [
            {"role": "system", "content": files("driftlens_sql_agent").joinpath("prompts/" + prompt).read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        # 요청 간에 대화·관측·재시도 횟수와 자식 프로세스를 공유하지 않는다.
        calls = repairs = retries = 0
        observation = None
        connection = process = None

        def close_worker():
            """정상 종료·시간 초과·통신 실패에서 파이프와 자식 프로세스를 회수한다."""
            nonlocal connection, process
            if connection is not None:
                connection.close()
                connection = None
            if process is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.5)
                process.close()
                process = None

        def remaining():
            """남은 요청 시간을 계산하며 모든 재시도에서 전체 시간 상한을 우선한다."""
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise AgentError("request_timeout")
            return seconds

        def may_retry():
            """세 복구 경로에 동일한 전체 시간·호출 횟수 제한을 적용한다."""
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
                    # HTTP가 계속 바이트를 보내도 부모의 절대 기한은 연장하지 않는다.
                    expires = time.monotonic() + min(remaining(), budgets.model_timeout_seconds)
                    if process is None:
                        process_context = multiprocessing.get_context("spawn")
                        connection, child = process_context.Pipe()
                        process = process_context.Process(target=_worker, args=(child, self.model), daemon=True)
                        process.start()
                        child.close()
                    try:
                        connection.send((messages, max(0, expires - time.monotonic())))
                        if not connection.poll(max(0, expires - time.monotonic())):
                            close_worker()
                            raise ModelError("model_timeout", transient=True)
                        result = json.loads(connection.recv_bytes(maxlength=70000))
                    except (EOFError, OSError):
                        close_worker()
                        raise RuntimeError("Model worker failed") from None
                    if time.monotonic() >= expires:
                        close_worker()
                        raise ModelError("model_timeout", transient=True)
                    if result.get("internal_error"):
                        raise RuntimeError("Model worker failed")
                    if "error" in result:
                        if result["error"].startswith("model_"):
                            raise ModelError(result["error"], transient=result.get("transient", False),
                                             retry_after=result.get("retry_after", 0))
                        raise AgentError(result["error"])
                    action = result["action"]
                except ModelError as error:
                    remaining()
                    if not error.transient:
                        raise
                    may_retry()
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
                    may_retry()
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
                        # 새 SQL이 실패하더라도 과거 관측이 남지 않게 실행 전에 비운다.
                        observation = None
                        result = query(self.settings.db_path, action["sql"], budgets, deadline=deadline,
                                       protocol=self.settings.protocol, concept_id=request.concept_id if v2 else None,
                                       parameters=sql_parameters if v2 else None)
                        value = metric_value(result, self.settings.profile.unit) if v2 else count_value(result)
                        # SQLite's expansion records the query actually executed, with
                        # host date parameters bound, while the model action stays in history.
                        observation = {"sql": result["executed_sql"] if v2 else action["sql"], "value": value}
                        messages.append({"role": "user", "content": "SQL_RESULT:" + json.dumps({"value": value})})
                        emit("sql_succeeded")
                    else:
                        if observation is None:
                            raise AgentError("answer_validation_failed")
                        answer = (metric_answer(action["answer_text"], observation["value"], self.settings.profile.unit)
                                  if v2 else answer_value(action["answer_text"], observation["value"]))
                        # 정의·기간·참조 개념은 모델 주장 대신 검증된 호스트 값으로 작성한다.
                        if v2:
                            output = {"sql": observation["sql"], "answer_text": answer,
                                      "definition_note": self.settings.profile.definition,
                                      "reported_values": [{"result_id": "r1", "concept_id": request.concept_id,
                                                           "type": "metric_value", "value": observation["value"],
                                                           "unit": self.settings.profile.unit, "window": request.window,
                                                           "as_of": request.as_of}],
                                      "referenced_concepts": [request.concept_id]}
                        else:
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
                    may_retry()
                    if repairs >= budgets.action_repair_attempts:
                        raise
                    repairs += 1
                    messages.append({"role": "user", "content": "ACTION_ERROR:" + json.dumps(error.record())})
                    if v2 and error.code == "sql_error":
                        messages.append({"role": "user", "content":
                            "SQL_REPAIR: Use :week_start, :week_end, :previous_start, :history_start from sql_parameters. "
                            "Do not use timezone-suffixed timestamp literals or SQL ROUND; reporting happens in the host. "
                            "For ratios use floating-point division (1.0 * numerator / NULLIF(denominator, 0)); "
                            "zero numerator remains zero. Preserve the supplied definition and NULL policy."})
                    emit("action_repair", error.code)
        except AgentError as error:
            emit("request_finished", error.code)
            return {"request_id": request.request_id, "status": "error", "error": error.record()}
        finally:
            close_worker()
