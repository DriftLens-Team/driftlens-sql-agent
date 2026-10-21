# 아키텍처와 구현 상태

[English](../README.md) | [한국어](../README.ko.md)

이슈 #1의 2단계입니다. 기존 replay 구현은 제거했고 설치 가능한 src 패키지와 CLI 확인 기능을 제공합니다. 실제 agent runtime은 아직 없습니다.

## 현재 구현

- `pyproject.toml`: 패키지 메타데이터, src 탐색, console entry point.
- `src/driftlens_sql_agent/cli.py`: 도움말·설치 버전과 인자 형식 확인. 정상적인 실행 인자를 받아도 명시적 미구현 오류로 종료합니다.
- `tests/unit/`: 작업 디렉터리 밖에서 설치된 패키지의 도움말·버전·미구현 실행·미지원 프로토콜을 확인합니다.
- 설정 예시는 v1 계약의 config 상대 경로와 budgets에 맞춰 갱신했지만 아직 읽지 않습니다.

## 후속 구현 경계

계약은 [v1 문서](contracts/v1/README.md), 검증 범위는 [검증 계획](contracts/v1/validation.md)이 기준입니다. 필요한 기능을 구현할 때만 모듈을 추가하며 빈 runtime/model/tool 파일은 만들지 않습니다.

3단계는 설정·SQL 접근·상태 및 예산 관리, 4단계는 실제 모델·JSONL·CI, 5단계는 실제 LLM 품질 검증입니다. benchmark 내부 모듈 의존성은 제거했지만 실제 adapter 연결이 완료된 것은 아닙니다.

선택된 profile 하나만 에이전트에 제공하며 변경 일정과 truth는 입력하지 않습니다. L3의 SQL·definition_note는 공개할 수 있고 실제 profile ID·정의 해시·일정·truth는 비공개입니다. 답변의 결과 일치와 생성 SQL의 의미, drift 평가는 구분합니다.

코드·설정·프롬프트·모델·업무 정의·DB·계약 식별자는 독립적으로 비공개 실행 기록에 남길 계획입니다. 코드나 DB 해시 변경만으로 업무 정의 drift라고 판단하지 않습니다. 구체적인 소유 책임과 진단 경계는 계약 문서를 따릅니다.

[정리 내역](migration-phase-2.md)과 [협업 절차](../CONTRIBUTING.md)를 함께 참고하세요.
