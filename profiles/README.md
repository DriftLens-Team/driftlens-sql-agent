# 업무 정의 예시

v1/v2는 코드 복제본이 아닌 업무 설정입니다. large_orders의 포함 비교(>=), 정수 센트 임계값, concept_id를 정의합니다. Python API의 load_settings가 선택된 하나를 로딩합니다. CLI에서도 시작 시 검증하여 로딩합니다.

관리자가 프로세스 시작 시 profile 하나를 선택합니다. 변경 일정과 truth는 포함하지 않고 profile 변경은 새 프로세스로 수행합니다. 탐지기는 별도로 기준 v1만 받으며 미래 v2와 실제 적용 profile은 전달하지 않습니다. 자세한 기준은 [계약 v1](../docs/contracts/v1/README.md)을 따릅니다.
