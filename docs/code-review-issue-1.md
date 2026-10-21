# 이슈 #1: 주석과 함수 사용처 검토

2026-10-21 사용자의 “각 코드별로 주석”, “3번 이상 사용된 코드 아니면 별도로 함수화하지 말자” 요청에 따른 후속 변경이다. 공통 규칙은 [CONTRIBUTING.md](../CONTRIBUTING.md)에 둔다. 검토 범위는 `src/`, `evaluation/`, `tests/`의 현재 Python 코드 전체다.

## 사용처 계산

서로 다른 호출 위치를 확인했다. 반복 횟수나 실행 횟수를 재사용 수로 세지 않는다. 기존 테스트도 실제 소비자로 포함했으며, 아래처럼 업무 실행 사용처와 구분한다. 사용 횟수를 채우기 위한 호출은 추가하지 않았다. 이름이 같은 `query`, `response`, `run`은 객체·import 대상을 구분했다.

경계에 해당하는 함수의 실제 사용처:

| 함수 | 실행·평가 코드 | 기존 테스트 | 합계 |
| --- | --- | --- | --- |
| load_settings | cli.main 1 | SettingsTests.load, test_profiles_and_duplicate_json 2 | 3 |
| validate_database | Runtime 생성자 1 | test_limits_and_schema의 누락 DB·잘못된 스키마 2 | 3 |
| serve | cli.main 1 | run_stream, test_internal_and_output_failures 2 | 3 |
| answer_value | Runtime.run, score 2 | test_strict_json_actions_and_answers 1 | 3 |
| expected | score의 기본·변형 데이터 비교 2 | test_fixed_corpus_and_gates 1 | 3 |
| may_retry | Runtime.run의 모델 일시 오류·action 오류·SQL/답변 오류 3 | 0 | 3 |
| error_response | serve의 프로토콜·중복/상한·업무 필드 오류 3 | 0 | 3 |

그 외 일반 함수 `record`, `strict_json`, `Request.parse`, `_keys`, `definition`, `query`, `count_value`, `emit`, `remaining`, `close_worker`, `write_response`, `digest`, `encode`, `score`, `corpus`와 테스트 헬퍼 `run_cli`, `load`, `query`, `scripted`, `completion`, `response`, `line`, `run_stream`은 각각 구분된 사용처가 3곳 이상이다. Runtime.run은 스트림 처리와 여러 기존 통합 테스트가 사용하는 요청 실행 경계다.

## 합친 로직

| 기존 추상화 | 변경 |
| --- | --- |
| _connect | 스키마 검사와 SQL 실행에서 read-only 연결 직접 생성 |
| retry_delay | UpstageModel.generate의 HTTPError 처리에 합침 |
| action_value | _worker의 모델 응답 검증에 합침 |
| Model Protocol | 실행에 쓰이지 않는 선언 제거; generate 인터페이스 유지 |
| ModelSession | 생성·호출 처리를 Runtime.run에 합침; 4개 종료 경로의 close_worker만 유지 |
| bounds / variants | 정답 계산 및 score의 변형 데이터 준비 위치에 합침 |
| make_db | 원본 fixture와 의미 검증 fixture 생성 위치에 합침 |
| evaluate | 평가 CLI main에 합침 |
| cleanup_server | unittest의 기본 addCleanup에 실제 정리 메서드를 직접 등록 |
| ProcessTests.command | 준비 훅 setUp에서 명령 목록을 구성; 미사용 인자 제거 |
| mock_adapter | 하나의 부모 계약 테스트에 시나리오별 처리를 합침 |

## 호출 형태가 필요한 예외

- `cli.main`, `evaluation.run.main`: 설치된 CLI와 모듈 실행 진입점.
- `__init__`, `__post_init__`: Python/dataclass가 호출하는 생성·검증 훅.
- `generate`: fake·Upstage·scripted 모델을 worker가 같은 방식으로 호출하는 인터페이스.
- `_worker`: Windows spawn에서 import 가능한 최상위 프로세스 진입점.
- `pairs`, `reject`, `number`: JSON 파서의 중복 키·비유한 수 검사 콜백.
- `_authorize`, `progress`: SQLite 권한·실행량 검사 콜백.
- `redirect_request`: urllib의 리다이렉트 차단 콜백.
- `diagnostic`: 스트림과 runtime에 전달하는 진단 출력 콜백.
- 테스트의 `test_*`, `setUp`, HTTP `do_POST`/`log_message`, 결함 주입용 `run`/`write`: 각 프레임워크가 요구하는 실행 훅.

## 주석과 동작 보존

모든 함수·메서드에 역할 docstring을 추가했다. 요청 격리, 절대 기한, 관측값 무효화, 호스트가 결정하는 정의, read-only 연결, HTTP 오류 지연, 평가 fixture 분리, 테스트 자원 회수 순서에는 이유를 설명했다.

CLI 옵션·JSONL 필드·설정 파일·SQL 권한·예산은 유지한다. 제거한 내부 헬퍼 이름은 외부 API로 유지하지 않는다. 문서에서 안내하던 `load_settings`와 `Runtime.run` 실행 방법은 유지한다. 실제 Upstage 품질은 별도 검증 대기 상태다.

검증 결과는 [검증 기록](verification.md)의 후속 리팩터링 항목을 참고한다.
