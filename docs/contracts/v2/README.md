# SemAlign agent/v2

이슈 [#18](https://github.com/DriftLens-Team/driftlens-sql-agent/issues/18)의 명시적 v2 모드다. 기본 모드와 기존 C03 계약은 v1을 유지한다. v2는 food/drink 주문 수, 활성/신규 고객 수, 평균 주문액, 전주 대비 매출 성장률, 평균 세율의 7개 개념을 지원한다. drift 판정과 생성 의미 검수는 benchmark가 수행한다.

## 실행과 설정

```powershell
.venv/Scripts/python.exe -m driftlens_sql_agent --capabilities
.venv/Scripts/python.exe -m driftlens_sql_agent --protocol-version v2 --config config.json --profile profile.json
```

`--capabilities`는 자격 증명 없이 프로토콜, 스키마, 개념, 코드·프롬프트 hash와 생성 설정을 출력한다. 서빙은 UTF-8 JSONL stdin/stdout을 사용한다. 진단은 stderr로 분리한다.

config 예:

```json
{
  "database": {"kind": "sqlite", "path": "snapshot.sqlite", "read_only": true},
  "schema_id": "semalign/v1",
  "model": {"provider": "fake", "id_env": "UPSTAGE_MODEL", "api_key_env": "UPSTAGE_API_KEY"}
}
```

DB 경로는 config 파일 기준이다. 실제 모델은 provider를 `upstage`로 설정하고 두 환경변수에 접근 가능한 모델 ID와 키를 제공한다. CLI는 `.env`를 자동 로드하지 않으며 키가 없으면 시작을 거부한다. 기존 quickstart의 환경 로딩과 구분한다. 기본 v2 SQL 예산은 2천만 VM 명령과 5초이며, 나머지는 기존 요청·모델·재시도 예산을 따른다. `budgets`로 명시적으로 조정할 수 있다.

profile 예:

```json
{
  "concept_id": "sa_order_value_avg",
  "label": "평균 주문액",
  "definition": "주간 주문의 세전 금액 평균",
  "unit": "cents",
  "semantics": {
    "grain": "order", "aggregation": "average", "population": "all",
    "measure": "subtotal_cents", "conditions": "none", "time_semantics": "week",
    "null_policy": "empty_is_null", "unit": "cents"
  }
}
```

현재 정의 하나만 입력한다. 버전 번호·미래 정의·변경 일정·truth·oracle은 허용 필드가 아니다. `fake`는 이 구조화 의미로 정해진 SQL을 만드는 통신 검증용 모델이다. 자연어 이해 성능으로 해석하지 않는다. 실제 모델에도 동일한 현재 profile만 전달한다.

## 입출력과 결과값

요청은 정확히 `request_id`, `request`, `timestamp`, `concept_id`, `window`, `as_of` 필드를 가진다.

```json
{"request_id":"demo-1","request":"주간 평균 주문액은?","timestamp":"2025-01-13T01:00:00Z","concept_id":"sa_order_value_avg","window":{"start":"2025-01-06T00:00:00Z","end":"2025-01-13T00:00:00Z"},"as_of":"2025-01-13T00:00:00Z"}
```

기간은 UTC 월요일 자정부터 다음 월요일 자정까지의 반열린 구간이며 `as_of=end`, 질문 시각은 end 이후다. SQL DB의 timestamp에는 시간대 접미사가 없으므로 문자열 비교에 `Z`를 그대로 붙이지 않는다. 호스트는 SQL용 날짜 경계를 별도 제공한다. snapshot 생성과 미래 행 제거는 호출자인 benchmark의 책임이다.

성공 응답은 기존 JSONL 봉투의 `observation`에 `request`, `answer`, `sql`, `reported_values`, `definition_note`를 담는다. reported_values는 개념·단위·window·as_of와 하나의 값이다. `count`는 0 이상의 signed 64-bit 정수, `cents`는 Python ties-to-even 반올림 정수, `ratio`는 소수 4자리 보고값, 계산 불가는 null이다. SQL 오류를 null로 변환하지 않는다. 결과 숫자는 유한해야 한다.

답변은 `결과는 123 cents입니다.` 또는 null일 때 `계산할 수 없습니다.` 형식을 검증한다. definition_note는 선택된 profile의 definition을 호스트가 기록하며 출처는 `profile_rendered`다. 자유 형식 모델 설명의 품질을 측정하는 경로는 아니다. SQLite SELECT/WITH와 개념별 허용 테이블·함수만 실행하며 다중 문장·쓰기·재귀 CTE는 거부한다.

값·답변이 실행 결과와 맞아도 SQL의 업무 의미가 맞다는 보장은 없다. 기계 판독 계약은 benchmark의 `contracts/agent/v2`와 `contracts/records/v3`를 참조하고, [검증 기록](validation.md)의 제한을 함께 적용한다. v1에 자동 강등하거나 v1 설정을 v2로 추측 변환하지 않는다.
