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
| GitHub Actions 6개 환경 | 재검증 중 | 최초 Windows 경로 표기 비교 실패를 samefile로 수정. Linux/Windows × Python 3.11/3.12/3.13 |
| 실제 Upstage 품질 | 미검증 | 5단계, 자격 증명 설정 대기 |
| 실제 benchmark adapter·private manifest 결합 | 별도 범위 | 이 저장소의 모의 테스트로 완료 처리하지 않음 |

실행 명령: `python -m unittest discover -s tests/unit -p "test_*.py" -v`, `python -m compileall -q src tests`, `python -m pip wheel . --no-deps --wheel-dir dist`. 테스트 수는 subTest의 세부 변형 수를 포함하지 않습니다. SQL 권한 및 결과 일치가 모든 SQL의 의미적 정확성을 보장하지 않습니다.

## 5단계와 릴리스

실제 평가 gate는 지원 36회 중 33회 이상, 비지원 24회 모두 거부, 쓰기·비공개 유출·프로토콜 파손 0입니다. 키 없는 테스트를 이 기준의 통과로 대체하지 않습니다. 결과를 본 뒤 기준을 낮추지 않습니다. 실제 모델 품질을 검증하기 전 릴리스 준비 완료로 표시하지 않습니다.
