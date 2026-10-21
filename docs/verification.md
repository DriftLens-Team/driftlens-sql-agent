# 이슈 #1 단계별 검증 기록

2026-10-21 사용자 지시: “해당 이슈의 내용들은 PR 승인까지 기다리지 말고 순서대로 작업해줘. 대신 각 요건 (테스트, 조건) 통과여부 상세하게 확인하고 단계별로 진행”. 선행 단계 검증 후 의존 브랜치에서 다음 단계를 진행하며 병합·릴리스는 자동 수행하지 않습니다.

## 1–3단계

- 1단계 계약·협업 규칙: PR #2 병합. benchmark 계약과 공개 10필드·UTC 기간·비공개 경계를 대조했습니다.
- 2단계 실험 코드 정리·패키지: PR #3 병합. 정리 목록은 migration-phase-2.md에 있습니다.
- 3단계 실행 코어: PR #4 제출, e229c0e. Windows/Python 3.11.9에서 editable 및 wheel 설치 각각 20개 테스트 통과. PR 병합과 무관하게 다음 단계 진행을 승인받았습니다.

## 4단계 요구사항별 결과

로컬 Windows/Python 3.11.9, 실제 API 키 없이 35개 테스트 통과. benchmark 계약 blob `785d1c81811650b3e818535f089fe694666711a6` 재확인: 변경 없음.

| 요구사항 | 결과 | 실행 증거 |
| --- | --- | --- |
| 설정·단위·매핑·readonly·키 누락·상대 경로 | 통과 | SettingsTests 3개, CLI 시작 실패 테스트 |
| 날짜·UTC/offset/naive·ISO 연도·요청 필드 | 통과 | SchemaTests 3개 |
| 실제 DB 읽기 전용/허용 테이블·함수/다중 문장 | 통과 | SqlTests.test_readonly_and_function_boundaries |
| SQL 길이·행 수·VM·스키마·잠금 | 통과 | SqlTests.test_limits_and_schema, test_locked_database_returns_promptly |
| SQL 시간/요청 deadline 우선순위 | 통과 | test_sql_deadline_precedes_sql_error (시간 경계 모의), 실제 모델/HTTP 중단 테스트 |
| 관측 무효화·답변 수정·요청 격리 | 통과 | RuntimeTests.test_repair_and_invalidated_observation, test_fake_profile_switch_and_isolation |
| 임계값 경계·기간 밖·빈 주·전부 미만·ISO 연말 | 통과 | test_profile_and_period_boundary_counts, test_generated_sql_semantic_variations; fake 생성 SQL 기준 |
| 마지막 호출 성공·재시도 합산·전체 timeout | 통과 | RuntimeTests의 호출/재시도/중단 테스트 |
| LF·CRLF·EOF 마지막 줄·BOM·UTF-8·중복 JSON 키·NaN | 통과 | TransportTests.test_framing_success_and_continuation, test_protocol_errors_stop_without_echo |
| 65,536 bytes 정확한 경계와 +1 | 통과 | test_exact_line_byte_limit (3가지 줄 끝), HTTP 초과 테스트 |
| 잘못된 요청 ID 예약·중복·max_requests | 통과 | test_duplicate_and_count_limit_reserve_invalid_ids |
| 즉시 flush·EOF 0·설정/프로토콜 2 | 통과 | ProcessTests; stdin을 닫기 전에 응답 수신 확인 |
| 내부 결함·출력 쓰기 실패 1·응답 크기 방어 | 통과 | test_internal_and_output_failures; 스트림 경계 fault injection |
| 실제 HTTP 형식·401/403/400/408/429/5xx·redirect | 통과 | HttpTests (loopback 서버, 외부 공급자 호출 아님) |
| 긴 Retry-After·연결 실패·응답 크기·잘못된 envelope | 통과 | HttpTests 및 RuntimeTests |
| 계속 도착하는 느린 HTTP 응답의 총 시간 | 통과 | test_http_retry_in_runtime_and_slow_stream_deadline |
| stdout 10필드 변환·오류 분리·누락/중복/비정상 종료 | 통과 | AdapterTests; 테스트 전용 부모, 실제 adapter 아님 |
| 비공개 진단·키/경로/원문 비노출 | 통과 | 고정 오류·메타데이터 테스트, provider repr·stdout/stderr 분리 |
| wheel 빌드·설치·문법 검사 | 통과 | 별도 wheel 환경에서 35개 통과, compileall·diff 검사 통과 |
| GitHub Actions 6개 환경 | 통과 | 2527cf7, [run 39617788292](https://github.com/DriftLens-Team/driftlens-sql-agent/actions/runs/39617788292), Linux/Windows × Python 3.11/3.12/3.13. 최초 Windows 경로 표기 실패를 samefile로 수정 후 전부 성공 |
| 실제 Upstage 품질 | 미검증 | 5단계, 자격 증명 설정 대기 |
| 실제 benchmark adapter·private manifest 결합 | 별도 범위 | 이 저장소의 모의 테스트로 완료 처리하지 않음 |

실행 명령: `python -m unittest discover -s tests/unit -p "test_*.py" -v`, `python -m compileall -q src tests`, `python -m pip wheel . --no-deps --wheel-dir dist`. 테스트 수는 subTest의 세부 변형 수를 포함하지 않습니다. SQL 권한 및 결과 일치가 모든 SQL의 의미적 정확성을 보장하지 않습니다.

## 5단계와 릴리스

실제 평가 gate는 지원 36회 중 33회 이상, 비지원 24회 모두 거부, 쓰기·비공개 유출·프로토콜 파손 0입니다. 키 없는 테스트를 이 기준의 통과로 대체하지 않습니다. 결과를 본 뒤 기준을 낮추지 않습니다. 실제 모델 품질을 검증하기 전 릴리스 준비 완료로 표시하지 않습니다.

평가 도구는 evaluation/에 별도로 구현했으며 runtime 배포 패키지에 평가 정답을 포함하지 않습니다. 실행 방법은 [평가 안내](../evaluation/README.md)를 따릅니다.

| 요건 | 결과 | 증거 |
| --- | --- | --- |
| 평가 전 데이터·질문·gate·생성 설정 고정 | 통과 | cases.py 및 호출 전 manifest 저장; 코드 c786c5e |
| 20사례 × 3회, 실패/거부도 분모 포함 | 통과 | 고정 corpus 테스트 및 60회 fake 리허설 |
| SQL 숫자 우연 일치 배제 | 통과 | SELECT 5는 기본 예상 5와 같아도 변형 DB에서 의미 실패 |
| 평가 정답·비공개 식별자 모델 입력 제외 | 통과 | subprocess에는 일반 요청/config/profile만 전달 |
| 재현 정보·호출 수·지연·실패 종류 기록 | 통과 | manifest/results/summary.private 파일, 키·원문 HTTP 제외 |
| editable 및 wheel 환경 자동 테스트 | 통과 | 각각 39개; 평가기 자체 테스트 4개 포함 |
| fake 60회 리허설 | 통과 | 지원 36/36, 비지원 거부 24/24, 위반 0, 모델 호출 96, 평균 205ms |
| 실제 Upstage 60회 | 대기 | 사용자가 환경변수 설정 후 알리기로 함. 아직 호출하지 않음 |
| live 품질 및 릴리스 gate | 미검증 | fake 결과의 live_quality_verified=false |

리허설 산출물은 Git 제외 경로 runs/phase5-offline-20261021/에 보관했습니다. 전체 이슈는 실제 평가와 결과 검토 전까지 완료 처리하지 않습니다. 이번 재설계는 실행 구조·CLI 전환이 필요한 큰 변경이므로 live 결과와 미해결 사항을 정리한 뒤 사용자에게 dev → main PR 진행을 요청해야 합니다.

## 후속 리팩터링: 주석과 함수 사용처

2026-10-21 사용자 요청에 따라 `refactor/1-comments-inline`에서 수행했다. 구현 커밋은 `b10ee18`, 상세 변경과 호출 위치·필수 콜백 예외는 [코드 검토 기록](code-review-issue-1.md)에 있다. 기존 PR #4 → #5 → #6의 누적 변경을 기반으로 하며, 이 변경 자체의 입력·출력 계약은 동일하다.

| 요건 | 결과 | 증거 |
| --- | --- | --- |
| 전체 Python 함수 설명 | 통과 | src/evaluation/tests 20개 파일 AST 확인, 함수·메서드 99개 모두 docstring 보유 |
| 3곳 미만 일반 헬퍼 정리 | 통과 | 단일 모델 호출·평가 실행 래퍼, DB 연결/생성, action/Retry-After 해석 등 호출 위치에 통합. 기존 테스트 포함 여부와 예외는 검토 문서에 명시 |
| 기존 실행 경계 회귀 | 통과 | Windows/Python 3.11.9 editable 테스트 40개, wheel 설치 테스트 40개 |
| 검증 코드 이동 후 경계 테스트 | 통과 | 잘못된 action은 worker를 통한 런타임 테스트, Retry-After는 loopback HTTP 테스트, SQL 경계는 평가 결과로 확인 |
| wheel 빌드·문법·공백 검사 | 통과 | pip wheel, compileall src tests evaluation, git diff --check |
| fake 평가 60건 | 통과 | 지원 36/36, 미지원 거부 24/24, 위반 0, 호출 96, 평균 202ms |
| 재현 가능한 평가 입력 | 통과 | clean b10ee18에서 실행, runs/refactor-offline-20261021/에 private manifest/results/summary 보관 |
| 원격 CI | 대기 | 이 변경의 PR에서 Linux/Windows × Python 3.11/3.12/3.13 결과 확인 필요 |
| 실제 Upstage 품질 | 미검증 | 환경변수 설정 완료 알림 대기. 이번 fake 평가로 live gate를 통과 처리하지 않음 |

실행: `python -m unittest discover -s tests/unit -p "test_*.py" -v`, `python -m compileall -q src tests evaluation`, `python -m pip wheel . --no-deps --wheel-dir .venv/refactor-dist`, 별도 wheel 환경 재설치 후 동일 테스트, `python -X utf8 -m evaluation.run --provider fake --output runs/refactor-offline-20261021`. 테스트 수에는 subTest 변형을 별도 합산하지 않는다.
