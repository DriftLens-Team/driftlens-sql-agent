"""Bounded per-request loop independent of stream framing and provider HTTP."""

from importlib.resources import files
import json
import multiprocessing
import time

from .errors import AgentError, ModelError
from .models import FakeModel, _worker
from .provider import UpstageModel
from .schemas import Request
from .settings import Settings
from .sql_access import query, validate_database
from .validation import answer_value, count_value


class Runtime:
    def __init__(self, settings: Settings, model=None):
        """생성자 훅: 이 인스턴스의 실행 상태와 검증된 의존성을 준비한다."""
        validate_database(settings.db_path)
        self.settings = settings
        if model is None:
            model = FakeModel() if settings.provider == "fake" else UpstageModel(settings.model_id, settings.api_key)
        self.model = model

    def run(self, obj, *, diagnostic=None):
        """요청마다 상태를 새로 만들고 모델 → SQL → 답변을 제한된 횟수 안에서 실행한다."""
        request = Request.parse(obj)
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
        context = {"question": request.question, "period": request.period,
                   "start": str(request.start), "end": str(request.end),
                   "definition": self.settings.profile.definition()}
        messages = [
            {"role": "system", "content": files("driftlens_sql_agent").joinpath("prompts/system.txt").read_text(encoding="utf-8")},
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
                        result = query(self.settings.db_path, action["sql"], budgets, deadline=deadline)
                        value = count_value(result)
                        observation = {"sql": action["sql"], "value": value}
                        messages.append({"role": "user", "content": "SQL_RESULT:" + json.dumps({"value": value})})
                        emit("sql_succeeded")
                    else:
                        if observation is None:
                            raise AgentError("answer_validation_failed")
                        answer = answer_value(action["answer_text"], observation["value"])
                        # 정의·기간·참조 개념은 모델 주장 대신 검증된 호스트 값으로 작성한다.
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
                    emit("action_repair", error.code)
        except AgentError as error:
            emit("request_finished", error.code)
            return {"request_id": request.request_id, "status": "error", "error": error.record()}
        finally:
            close_worker()
