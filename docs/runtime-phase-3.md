# 3단계 실행 코어

설정·SQL 도구·bounded loop를 Python API로 사용할 수 있습니다. 이 문서는 3단계 Python API를 설명합니다. 4단계의 CLI와 Upstage 연결은 [실행 안내](running.md)를 참고하세요.

## 오프라인 실행

1. 패키지를 설치합니다: `python -m pip install -e .`
2. `configs/runtime.example.json`을 `configs/offline.json`으로 복사하고 `model.provider`를 `fake`로 변경합니다. DB path는 **복사한 config 위치 기준**으로 지정합니다. 환경변수 이름 키는 유지하되 fake에는 실제 키가 필요하지 않습니다.
3. 계약의 orders 스키마를 가진 SQLite 파일을 준비합니다. profile은 v1/v2 중 하나를 선택합니다.
4. 아래를 Python 파일로 저장하고 실행합니다. 프로세스 격리를 위해 `__main__` 가드가 필요합니다. 대화형 셸·노트북에서 직접 실행하는 방식은 검증하지 않았습니다.

```python
from driftlens_sql_agent.settings import load_settings
from driftlens_sql_agent.runtime import Runtime

if __name__ == "__main__":
    settings = load_settings("configs/offline.json", "profiles/v1/profile.example.json")
    runtime = Runtime(settings)
    result = runtime.run({
        "request_id": "demo-1",
        "request": "이번 주 대형 주문은 몇 건인가요?",
        "period": "2025-W03",
        "timestamp": "2025-01-19T23:59:59Z",
    })
    print(result)
```

fake는 검증 계획의 한국어 질문 3개만 인식하고 나머지는 unsupported_request로 거부합니다. 자연어 이해 성능을 대신하지 않습니다. upstage 설정은 키를 검증하고 실제 HTTP 모델을 생성하며 fake로 전환하지 않습니다.

## 동작과 경계

- config·profile은 불변 설정으로 읽고 시작 시 orders 스키마를 확인합니다. 예산은 계약 기본값 이하로만 낮출 수 있습니다.
- 모델 입력은 시스템 프롬프트·현재 질문/기간·선택 정의·현재 요청의 행동/결과입니다. 모델 객체는 spawn으로 복제되므로 사용자 정의 테스트 모델은 import 가능한 모듈에 정의해야 합니다.
- SQL은 SELECT, orders, COUNT만 허용하는 권한 검사와 읽기 전용 연결을 사용합니다. 이것은 기간·임계값이 옳다는 증명이 아닙니다. 조인은 지원 질문 범위 밖이며 프롬프트에서 거부합니다. SQL 도구는 모든 SQL 구문에 대한 의미 검사기가 아닙니다.
- 결과는 비음수 정수 하나여야 합니다. 새 query 또는 잘못된 action은 기존 observation을 무효화합니다. 답변 표현만 잘못됐다면 관측값을 유지하며 예산 안에서 복구합니다.
- 답변은 제한된 한국어 문장 형식으로 검증합니다. 선택 접두어는 `이번 주 `, `해당 주의 `, `주간 `이고 본문은 `대형 주문은 N건입니다.`, `대형 주문 수는 N건입니다.`, `대형 주문 건수는 N건입니다.`입니다. 일반적인 한국어 문장 전체를 지원하지 않습니다.
- 모델 호출은 요청별 별도 프로세스에서 실행하며 시간 초과 시 종료합니다. 프로세스 시작 시간도 호출 예산에 포함합니다. 종료 정리에 짧은 추가 시간이 들 수 있습니다.
- 정상 요청의 실행 오류는 status=error와 고정 메시지로 반환합니다. 잘못된 요청은 Request.parse의 AgentError, 예상하지 못한 내부 오류는 예외로 호출자에게 전달합니다. 종료 코드와 스트림 오류 처리는 transport가 담당합니다.
- diagnostic 콜백에는 request_id·stage·elapsed_ms·code만 전달합니다. 키·SQL·원문 질문·모델 응답은 포함하지 않습니다. private manifest 저장은 별도 연결 예정입니다.
- ID 중복 거부, JSONL 바이트/줄 검증, max_requests 적용은 transport가 처리합니다. 이 코어 API는 같은 ID를 재사용해도 매번 새 요청으로 실행합니다.

자동 테스트는 임시 SQLite와 fake/scripted 모델로 실행했습니다. 실제 모델 품질, live HTTP, 실제 benchmark adapter는 미검증입니다.
