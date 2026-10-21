# 아키텍처와 구현 상태

## 재설계 기준

이슈 #1의 새 구현은 [계약 v1](contracts/v1/README.md)과 [검증 계획](contracts/v1/validation.md)을 따른다. 아직 계약 문서 단계이며 아래 기존 replay 구현과 구분한다. 공통 협업 절차는 [CONTRIBUTING.md](../CONTRIBUTING.md)를 따른다. 기존 주석 전용 engine과 설정 예시의 정리는 후속 단계다.

[English overview](../README.md) | [한국어 개요](../README.ko.md)

이 문서는 현재 실행 경로와 계획된 구성요소의 책임, 정보 경계, 버전 기록을 설명한다. 설정 예시와 주석 전용 Python 파일은 설계 안내이며 실행 기능을 제공하지 않는다. 실제 사용 방법은 저장소 루트 README를 따른다.

현재 agent.py는 공개 benchmark 로그의 SQL을 replay하며 benchmark의 driftlens·public_logs·sql_tool을 import한다. test_agent.py는 현재 replay 동작을 검증한다. 향후 engine 공통 엔진이 질문을 처리하고 업무 정의·DB·스키마·단위·모델 설정을 읽도록 분리할 예정이다. 의존성 제거와 독립 text-to-SQL은 아직 구현되지 않았다.

| 경로 | 역할 |
| --- | --- |
| ../engine/README.md | 공통 실행·조회·통신 경계 |
| ../profiles/README.md | v1/v2 업무 정의 설정 |
| ../prompts/README.md | 공통 지시문 구성 원칙 |
| ../configs/README.md | DB·매핑·단위·모델 예시 |
| ../tests/README.md | 후속 검증 범위 설명 |

[benchmark 저장소](https://github.com/DriftLens-Team/driftlens-benchmark)의 contracts/v1/README.md가 향후 JSONL 프로세스 연결 계약의 기준이다. benchmark가 agent를 별도 프로세스로 호출하고 각 저장소는 서로 내부 모듈을 import하지 않는 것을 목표로 한다. 현재 agent stdout은 해당 미래 계약이 아니다.
관리자가 선택한 profile 하나만 agent 실행에 제공한다. 탐지기는 공개 로그와 기준 v1만 받으며 미래 v2·실제 profile·변경 시점·truth는 평가 전용으로 분리한다. agent에 변경 일정이나 truth를 전달하지 않는다. 생성 관리자는 실험 생성을 위해 일정과 profile을 선택할 수 있다.

## 독립적인 버전 기록 (향후 계획)
코드 변경·DB 변경을 업무 정의 변경과 혼동하지 않도록 다음 축을 서로 독립적으로 private run metadata에 기록한다. 기존 공개 로그 10필드와 truth 4필드는 확장하지 않는다.

| 축 | 기록할 식별자 |
| --- | --- |
| agent 코드 | agent_repo_commit |
| 실행 설정 | profile_id, config_hash |
| 프롬프트·모델·생성 조건 | prompt_hash, model_id, generation_settings |
| 업무 정의 | ontology_version_used, definition_hash |
| DB·데이터와 매핑 | dataset_id, snapshot_hash, schema_mapping_hash |
| 탐지기 | detector_version, detector.config_hash |
| 교환 계약 | contract_version |

설정의 config_hash와 탐지기 config_hash는 별도 영역으로 구분한다. 코드 커밋, DB 스냅샷 또는 매핑 해시가 바뀌어도 그것만으로 업무 정의 변경이나 contaminated=true를 뜻하지 않는다. 정의 버전과 해시를 별도로 비교한다. 이 기록 방식은 향후 계획이며 현재 자동 기록 기능은 없다.
실제 실행 profile, 미래 정의, 실제 변경 시점은 비공개 실행 기록에만 두고 공개 agent_id나 파일명에 인코딩하지 않는다. agent_id는 실제 적용 버전을 누설하지 않는 안정적인 식별자로 유지한다. 생성 관리자는 선택된 설정으로 실행하고 evaluator만 평가 시 비공개 기록과 정답을 읽는다. 탐지기는 자신의 버전·설정 외에 허용 공개 로그와 기준 v1만 받는다.
