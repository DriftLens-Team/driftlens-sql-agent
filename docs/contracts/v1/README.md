# SQL 에이전트 계약 v1

상태: 이슈 [#1](https://github.com/DriftLens-Team/driftlens-sql-agent/issues/1)의 1단계에서 정의한 구현 기준. 3단계 코어와 4단계 Upstage·JSONL 구현의 기준이다. 요건별 실제 검증 결과와 미검증 범위는 [검증 기록](../../verification.md)을 따른다.

## 기준과 범위

- Python 3.11 이상, SQLite 단일 DB, `orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER)`를 대상으로 한다.
- `ordered_at`은 benchmark가 정규화한 UTC 날짜 `YYYY-MM-DD`, 금액은 정수 센트다. CSV 변환은 benchmark의 책임이다.
- 시나리오 A의 `large_orders` 주간 건수만 지원한다. 결과는 음수가 아닌 정수 스칼라 하나이며 bool·실수·문자열·NULL은 허용하지 않는다.
- profile의 `comparison`은 `>=`, `concept_id`는 `large_orders`, `amount_unit`은 `integer_cents`, `threshold`는 음수가 아닌 정수다.
- SQL은 모델이 질문과 선택된 업무 정의로 생성한다. 기존 SQL replay, 범용 분석·합계·조인·다른 테이블은 첫 구현에서 제외한다.
- 모델은 한국어 주간 대형 주문 건수 요청을 처리한다. 범위 밖이거나 모호한 질문은 `unsupported_request`로 종료한다. 기간은 아래 구조화된 `period`가 기준이며, 질문에 명시한 기간·임계값과 충돌하면 질문으로 설정을 덮어쓰지 않고 거부한다. 자유 문장 판별의 한계는 평가에서 별도 보고한다.

## benchmark와의 경계

[benchmark 계약 v1](https://github.com/DriftLens-Team/driftlens-benchmark/blob/main/contracts/v1/README.md)을 2026-10-21에 대조했다. 당시 파일의 Git blob SHA는 `785d1c81811650b3e818535f089fe694666711a6`이다. 후속 구현 시 계약 변경 여부를 확인한다.

benchmark가 이미 정의한 사항은 요청·응답의 예정 필드, 공개 로그 10필드, UTC 주간 의미, 공개/비공개 경계다. 이 문서가 구체화한 status 값·오류 구조·프레이밍·예산·종료 규칙은 **agent 측 v1 규칙**이며 아직 구현되지 않은 benchmark adapter에 반영되었다고 가정하지 않는다.

이번 저장소의 범위는 에이전트 구현과 모의 부모 프로세스에 의한 연결 검증까지다. 실제 benchmark adapter 구현·두 저장소의 종단간 실행은 별도 작업이다. 서로의 내부 Python 모듈을 import하지 않는다.

프로토콜 버전은 관리자가 프로세스 시작 시 `--protocol-version v1`로 선택하며 생략 시 v1이다. 지원하지 않는 버전은 시작 실패다. 요청·응답 봉투에 버전 필드를 추가하지 않는다. 양측의 버전 선택과 agent 커밋을 비공개 실행 기록에 남긴다.

## 실행 설정

새 진입점은 패키지 설치 후 `driftlens-sql-agent --config <path> --profile <path> --protocol-version v1`이다. 4단계에서 이 명령을 JSONL 실행에 연결했다.

- config와 profile 경로는 필수 CLI 인자다. 시작 시 한 번 읽고 검증하며 프로세스 중 변경하지 않는다. profile 변경은 새 프로세스로 수행한다.
- config의 DB 상대 경로는 **config 파일의 부모 디렉터리 기준**이다. config/profile CLI 상대 경로만 현재 작업 디렉터리 기준으로 해석한다.
- 모델 provider는 첫 구현에서 `upstage` 또는 `fake`다. fake는 테스트 더블이고 실제 모델 실패의 자동 대체 수단이 아니다.
- DB는 읽기 전용이며 스키마는 위 고정 스키마로 한정한다. 기존 예시의 schema_mapping은 해당 고정 매핑만 허용하고 다른 매핑은 설정 오류로 처리한다. 금액 단위 변환과 DB별 방언 지원은 후속 범위다.
- 모델 ID와 API 키는 config가 지정한 환경변수에서만 가져온다. 실제 비밀 값은 저장소에 넣지 않는다. LLM 모드에서 누락된 자격 증명은 시작 실패다.
- 요청에서 config/profile/DB/model을 지정할 수 없다. 알 수 없는 설정 키, 잘못된 타입, 단위 불일치, 읽기 전용 해제는 시작 실패다.
- config의 선택적 `budgets` 객체는 아래 표와 같은 키를 사용한다. 생략된 값은 기본값, 지정 값은 양의 정수이며 기본값 이하만 허용한다. 상한 확대는 별도 계약 검토 대상이다.
- profile, DB 스냅샷은 관리자가 통제한다. DB는 실행 중 불변 스냅샷이어야 한다. 읽기 전용 연결만으로 다른 프로세스의 수정을 막았다고 주장하지 않는다.

## 요청

UTF-8 JSONL, 한 줄에 객체 하나. 정확히 다음 네 필드만 허용한다.

| 필드 | 규칙 |
| --- | --- |
| `request_id` | `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` 문자열. 같은 프로세스 내 재사용 금지 |
| `request` | 공백만 아닌 문자열, 최대 4,096 Unicode 문자 |
| `timestamp` | ISO 8601 날짜·시각. 오프셋은 UTC로 정규화하고 오프셋이 없으면 UTC로 가정했다는 진단을 남김 |
| `period` | 유효한 ISO 주차 `YYYY-Www` 문자열. ISO 주차 연도 기준 |

timestamp는 period의 일요일 `23:59:59` UTC와 일치해야 한다. 소수 초는 허용하지 않는다. 기간 조회는 월요일 `00:00:00` 포함부터 다음 월요일 제외다. 프로세스에 주입된 profile 하나를 주 전체에 적용한다. 변경 일정으로 profile을 선택하는 것은 관리자의 책임이며 에이전트는 일정이나 truth를 받지 않는다.

```json
{"request_id":"req-001","request":"이번 주 대형 주문은 몇 건인가요?","timestamp":"2025-01-19T23:59:59Z","period":"2025-W03"}
```

JSON의 중복 키, NaN/Infinity, 추가 필드는 거부한다. 한 번에 하나씩 순차 처리하며 응답 순서는 입력 순서다. 요청 본문과 모델 출력은 지시 권한이 있는 설정으로 취급하지 않는다.

## 성공 응답

정확히 `request_id`, `status`, `observation`을 포함한다. `status`는 `ok`다. observation은 다음 다섯 필드만 가진다.

| 필드 | 규칙 |
| --- | --- |
| `sql` | 마지막 성공 관측을 만든 실제 실행 SQL 문자열 |
| `answer_text` | 실제 건수 한 번만 포함하는 한국어 답변. 금액·정의·버전·변경 시점·비교 설명 제외 |
| `definition_note` | 선택된 업무 정의의 설명. profile ID·변경 일정·truth·해시 제외 |
| `reported_values` | `{concept_id, value, period}` 객체 하나의 배열. concept_id는 large_orders, value는 실제 SQL 결과, period는 요청과 동일 |
| `referenced_concepts` | 정확히 `["large_orders"]` |

아래는 합성 예시다. 실제 DB를 실행한 결과를 주장하지 않는다.

```json
{"request_id":"req-001","status":"ok","observation":{"sql":"SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-01-13' AND ordered_at < '2025-01-20' AND order_total_cents >= 3000","answer_text":"이번 주 대형 주문은 2건입니다.","definition_note":"주문 총액 3000센트 이상인 주문","reported_values":[{"concept_id":"large_orders","value":2,"period":"2025-W03"}],"referenced_concepts":["large_orders"]}}
```

reported_values와 definition_note는 검증된 관측·선택된 profile로 호스트가 구성한다. 모델이 임의로 출력한 메타데이터를 그대로 전달하지 않는다. 답변의 숫자 일치는 SQL의 업무 의미가 정확함을 보장하지 않는다.

adapter는 이 응답을 request_id로 요청에 연결하고 log_id·timestamp·agent_id·team·request와 observation을 조합하여 기존 공개 로그 10필드를 만든다. 봉투 전체를 공개 로그로 저장하지 않는다. 에이전트는 log_id나 drift 라벨을 생성하지 않는다.

## 오류 응답 및 프로세스 종료

정확히 `request_id`, `status`, `error`를 포함하며 status는 `error`다. error는 `code`, `message` 두 문자열만 가진다. message는 코드에 대응하는 고정된 짧은 설명이며 원본 입력·예외 문자열·DB 경로·키·HTTP 본문을 포함하지 않는다.

```json
{"request_id":"req-002","status":"error","error":{"code":"unsupported_request","message":"Only weekly large-order counts are supported."}}
```

| 오류 코드 | 처리 |
| --- | --- |
| `invalid_request` | 유효한 JSON 객체·ID이나 필드/기간/타입이 잘못됨. 해당 ID로 오류 응답 후 다음 줄 처리 |
| `unsupported_request` | 지원 범위 밖·모호하거나 구조화된 기간/정의와 충돌하는 질문. 재시도 없이 해당 요청 종료 |
| `model_auth_failed` | 인증·권한 실패. 재시도 없이 해당 요청 종료 |
| `model_request_failed` | 재시도 불가능한 HTTP 오류, 또는 전송/429/5xx 재시도 소진 |
| `model_timeout` | 개별 모델 호출 시간 초과의 재시도 소진 |
| `invalid_action` | 모델 JSON/행동 형식 오류의 수정 기회 소진 |
| `sql_error` | SQL 거부/실행 실패/결과 모양 오류의 수정 기회 소진 |
| `answer_validation_failed` | 성공 관측 없는 답변 또는 숫자·답변 정책 오류의 수정 기회 소진 |
| `turn_limit` | 모델 호출 횟수 소진 |
| `request_timeout` | 요청 전체 시간 소진 |
| `protocol_error` | 파싱 불가, 중복 키, 잘못된 UTF-8, 빈 줄, 잘못된/없는 ID, 최대 줄 크기 초과 |
| `duplicate_request_id` | 이미 수신한 ID 재사용. 실행하지 않고 오류 응답 후 종료 |
| `request_limit` | 프로세스 요청 수 한도 초과. 실행하지 않고 오류 응답 후 종료 |

유효한 ID가 있는 JSON 객체는 다른 필드가 잘못되었어도 ID를 예약한다. invalid_request를 받은 ID도 재사용할 수 없다. protocol_error는 상관관계를 신뢰할 수 없어 request_id를 null로 출력하고 즉시 종료한다. duplicate_request_id는 중복 ID를 그대로 반환하되 즉시 종료하므로 부모 프로세스는 해당 세션을 프로토콜 실패로 처리한다.

- 입력 줄 최대 65,536 bytes(줄바꿈 제외), 모델 응답 최대 65,536 bytes, 출력 JSONL 한 줄 최대 65,536 bytes다. 넘는 모델 응답은 invalid_action으로 처리한다.
- LF와 CRLF를 허용하며 EOF 직전 마지막 줄은 줄바꿈 없이도 처리한다. UTF-8 BOM은 허용하지 않는다. 한 줄 크기를 넘으면 계속 버퍼링하지 않고 종료한다.
- 정상 EOF는 종료 코드 0이다. 요청별 업무/모델/SQL 실패가 있어도 오류 응답을 정상 전달했다면 종료 코드 0이며 부모는 각 status를 확인한다.
- 설정·DB 사전 검증·버전 실패는 stdout 없이 stderr 진단 후 종료 코드 2다. protocol_error·duplicate_request_id·request_limit는 가능한 오류 응답 한 줄을 flush한 뒤 종료 코드 2다.
- 예상하지 못한 내부 결함·출력 쓰기 실패는 stderr 진단 후 종료 코드 1이다. 정상 오류 응답이나 계속 처리를 보장하지 않으며 부모는 미응답 요청을 실패로 기록한다.
- 정상 요청은 성공 또는 실패 응답 정확히 하나를 받고 flush한다. 시작 실패·강제 종료·내부 결함은 예외다. 부모는 응답 누락과 프로세스 종료를 검사해야 한다.
- stdout은 프로토콜만, stderr는 비공개 진단만 쓴다. 오류는 공개 성공 로그나 drift 양성으로 변환하지 않는다.

## 모델·도구·상태 계약

모델 어댑터는 대화 메시지와 남은 시간/응답 크기 제한을 받아 JSON 행동 하나 또는 분류된 모델 오류를 반환한다. FakeModel도 같은 인터페이스를 사용한다. 공급자용 HTTP 처리·JSON 파싱과 반복 실행을 분리한다.

모델 행동은 다음 셋 중 하나이며 추가 키는 허용하지 않는다.

```json
{"action":"query","sql":"SELECT COUNT(*) FROM orders"}
```

```json
{"action":"answer","answer_text":"이번 주 대형 주문은 2건입니다."}
```

```json
{"action":"unsupported"}
```

query 예시는 행동 형태만 나타내며 주간·임계값 필터가 없는 SQL은 의미 평가를 통과하지 못한다. unsupported는 unsupported_request로 종료한다. question/period/profile/schema가 프롬프트에 주입되지만 비공개 식별자와 truth는 넣지 않는다.

SQL 도구는 SQL·DB 핸들·남은 예산을 받아 columns와 rows 또는 분류된 오류를 반환한다. 단일 SELECT만 허용하고 orders 읽기와 COUNT만 필요한 최소 권한을 제공한다. 쓰기, DDL, ATTACH, PRAGMA, 확장 로딩, 시스템/다른 테이블, 다중 문장은 거부한다. 정규식만으로 읽기 전용 권한을 보장하지 않고 SQLite 읽기 전용 연결과 authorizer 등 실행 시 제약을 적용한다.

runtime은 SQL 결과가 1행 1열의 음수가 아닌 정수인지 확인한다. 새로운 query를 처리하기 전에 기존 관측을 비운다. 성공하면 해당 SQL·값만 최신 관측으로 저장하고 실패 시 비워둔다. 잘못된 모델 행동도 관측을 무효화한다. 다음 답변은 최신 성공 관측을 기준으로 검증한다. 답변 실패의 수정은 그 관측을 유지할 수 있다.

요청 시작마다 messages·observation·오류 횟수·예산을 새로 만들고 종료 후 폐기한다. ID 중복 검사용 집합은 대화 기억이 아닌 프로토콜 메타데이터로 프로세스 동안 유지한다. 도구/모델 객체 재사용 시에도 이전 대화·결과를 저장하지 않는다.

## 실행 예산과 재시도

| config budgets 키 | 기본값 및 상한 | 의미 |
| --- | --- | --- |
| `max_model_calls` | 5 | 전송 재시도를 포함한 실제 모델 호출 총 횟수 |
| `request_timeout_seconds` | 60 | 요청 유효성 검사를 마친 뒤 응답 생성까지 전체 처리 시간 |
| `model_timeout_seconds` | 20 | 모델 호출 하나의 총 시간. 남은 요청 시간과의 최솟값 적용 |
| `model_transient_retries` | 1 | 요청 전체에서 연결 실패·timeout·429·5xx에 허용되는 추가 호출 수 |
| `action_repair_attempts` | 1 | 요청 전체에서 invalid_action·sql_error·answer_validation_failed에 대한 수정 호출 기회 합계 |
| `sql_timeout_seconds` | 2 | SQL 한 호출의 최대 시간. 남은 요청 시간과의 최솟값 적용 |
| `sql_vm_steps` | 100000 | SQL 한 호출의 VM 명령 상한. 진행 콜백 주기에 따른 근사 제한이며 상한 근처에서 중단 |
| `sql_max_chars` | 10000 | SQL 문자열 최대 문자 수 |
| `sql_max_rows` | 100 | SQL 도구 결과 상한. runtime의 성공 요건은 별도로 1행 1열 |
| `max_requests` | 10000 | 프로세스당 유효한 ID를 가진 최초 요청 수. ID 집합의 무한 증가 방지 |

재시도 두 항목은 예외적으로 0도 허용한다. 모든 재시도·수정·대기는 전체 시간과 모델 호출 상한을 공유한다. transient 재시도 전 대기는 최대 1초이며 Retry-After가 더 길면 자동 대기하지 않고 model_request_failed로 종료한다. 인증/잘못된 설정/지원 범위 밖 요청은 재시도하지 않는다.

오류를 모델에 돌려주는 경우 원본 예외 대신 안전한 오류 코드와 고정 설명만 전달한다. 오류를 숨기거나 실패를 fake 성공으로 바꾸지 않는다.

종료 우선순위: 전체 시간이 끝났으면 request_timeout, 다음 모델 호출이 필요하나 호출 수가 없으면 turn_limit, 해당 오류의 수정/재시도 기회가 없으면 원래 오류 코드다. 마지막 허용 호출에서 유효한 최종 답변이 나왔으면 전체 시간 안에서 성공할 수 있다.

시간은 단조 시계로 측정한다. 네트워크의 단순 read timeout만으로 총 제한을 보장하지 않는다. 후속 구현은 총 deadline과 취소/연결 해제 또는 종료 가능한 실행 경계를 적용하고, 느린 스트림/잠금/중단되지 않는 호출을 검증해야 한다. stdin 대기 시간은 요청 처리 예산에 포함하지 않으며 부모 프로세스의 별도 감시 대상이다.

## 공개 관측·비공개 진단

L3의 sql과 definition_note는 업무 정의 단서를 의도적으로 공개한다. profile ID·정의 해시·변경 일정·truth·모델 원문은 공개 봉투/로그에 추가하지 않는다. answer_text에는 실제 건수만 둔다.

비공개 진단은 request_id, 단계, 오류 코드, 소요 시간, 종료 사유를 기본으로 한다. SQL·모델 원문·전체 요청은 기본 진단에서 제외하고, 재현에 필요한 SQL은 성공 observation 또는 통제된 테스트 산출물로 확인한다. API 키는 어떤 진단에도 기록하지 않는다.

관리자는 agent commit, protocol version, 모델 ID/생성 설정, config/profile/prompt/DB의 식별자·해시를 비공개 실행 메타데이터로 기록한다. 에이전트는 시작 시 자신이 읽은 설정과 리소스의 비밀 값 제외 식별자를 stderr에 보고할 수 있다. adapter의 메타데이터 결합은 별도 구현 대상이다. 탐지기에 stderr나 시작 설정을 전달하지 않는다.

선택된 v2 정의에 맞게 SQL을 생성한 것은 생성 성공이다. 기준 v1 대비 업무 정의가 달라졌는지를 평가하는 drift와 별개다. 계산 오류나 hallucination을 contaminated=true로 해석하지 않는다.

## 변경과 완료 판단

요청·응답의 필드/타입/의미를 깨는 변경은 새 계약 버전과 명시적 검토가 필요하다. 이 문서의 agent 측 세부 규칙을 benchmark가 구현했다고 주장하지 않는다. [검증 계획](validation.md)의 기준을 만족한 범위를 PR에 기록한다.

실제 LLM 평가를 실행하지 못하면 키 없는 테스트 통과로 구현 PR은 검토할 수 있지만 실제 품질과 릴리스 준비는 미검증으로 남긴다. 단계 진행은 CONTRIBUTING.md와 사용자 승인 범위를 따른다. 이슈 #1은 2026-10-21 사용자 지시에 따라 단계별 검증 뒤 PR 병합 대기 없이 순차 진행한다. main 반영은 별도 릴리스 승인 절차를 따른다.
