# 아키텍처와 구현 상태

이슈 #1의 4단계입니다. [검증 기록](verification.md)에서 실제 통과 여부를 확인합니다. [Python API 실행 안내](runtime-phase-3.md)와 [계약 v1](contracts/v1/README.md)을 참고하세요.

| 모듈 | 구현 역할 |
| --- | --- |
| settings.py | config·단일 profile·고정 매핑·예산 검증, config 상대 DB 경로 |
| schemas.py | 중복 키·비유한 수 거부, 요청 ID·ISO 주·주말 timestamp 검증 |
| sql_access.py | 읽기 전용 SQLite, 권한 검사, 시간·VM·길이·행 수 제한 |
| models.py | fake 모델, 자식 프로세스 진입점과 action 검사 |
| runtime.py | 요청별 프로세스·시간 제한·재시도·복구 예산, 관측값 무효화, 응답과 진단 |
| validation.py / errors.py | 단일 정수 결과·답변 검사, 고정 오류 메시지 |
| prompts/system.txt | 모델에 전달할 스키마·정의·주간 범위·행동 규칙 |
| provider.py | Upstage HTTP, 응답 크기 제한, 오류 분류, redirect 차단 |
| transport.py | JSONL 바이트·ID·요청 수·flush·종료 코드 |
| cli.py | 시작 설정 검증과 JSONL 실행 |

상태와 모델 프로세스는 요청별로 새로 만듭니다. 선택된 profile 하나만 제공하고 truth·변경 일정·미래 profile은 전달하지 않습니다. 빈 agents/memory/planner 폴더는 만들지 않습니다.

L3의 SQL·definition_note는 공개할 수 있습니다. 조회 결과와 답변의 일치는 SQL 의미 검증 또는 drift 평가를 대신하지 않습니다. 잘못된 기간·조건을 생성하는 문제는 [검증 계획](contracts/v1/validation.md)의 별도 평가 대상입니다.

Upstage 연결·JSONL·CI 설정을 구현했습니다. 5단계는 live 품질 검증입니다. private 실행 manifest와 실제 benchmark adapter도 현재 완료로 간주하지 않습니다. benchmark 내부 import는 없습니다.

[2단계 정리 내역](migration-phase-2.md)과 [협업 절차](../CONTRIBUTING.md)를 참고하세요.
