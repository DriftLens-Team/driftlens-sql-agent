"""Stable, non-sensitive errors at component boundaries."""

MESSAGES = {
    "invalid_config": "Invalid startup configuration.",
    "invalid_request": "Invalid request fields or period.",
    "protocol_error": "Invalid protocol object or identifier.",
    "duplicate_request_id": "Request identifier already used.",
    "request_limit": "Process request limit exceeded.",
    "unsupported_request": "Only weekly large-order counts are supported.",
    "model_auth_failed": "Model authentication failed.",
    "model_request_failed": "Model request failed.",
    "model_timeout": "Model request timed out.",
    "invalid_action": "Invalid model action.",
    "sql_error": "SQL query rejected or failed.",
    "answer_validation_failed": "Answer does not match the latest observation.",
    "turn_limit": "Model call budget exhausted.",
    "request_timeout": "Request time budget exhausted.",
}


class AgentError(ValueError):
    def __init__(self, code: str):
        """생성자 훅: 이 인스턴스의 실행 상태와 검증된 의존성을 준비한다."""
        self.code = code
        super().__init__(MESSAGES[code])

    def record(self) -> dict:
        """내부 예외 문자열 대신 외부 공개가 허용된 고정 코드와 메시지를 반환한다."""
        return {"code": self.code, "message": MESSAGES[self.code]}


class ModelError(AgentError):
    def __init__(self, code: str, *, transient: bool = False, retry_after: float = 0):
        """생성자 훅: 이 인스턴스의 실행 상태와 검증된 의존성을 준비한다."""
        if code not in {"model_auth_failed", "model_request_failed", "model_timeout"}:
            raise ValueError("Invalid model error code")
        super().__init__(code)
        self.transient = transient and code != "model_auth_failed"
        self.retry_after = retry_after
