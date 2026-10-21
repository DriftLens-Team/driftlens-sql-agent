# 런타임 설정 예시

`runtime.example.json`은 [계약 v1](../docs/contracts/v1/README.md)에 맞춘 미래 설정이며 현재 CLI는 파일을 로딩하지 않습니다.

DB 상대 경로는 config 파일의 부모 디렉터리가 기준입니다. 이 예시가 저장소의 configs 안에 있을 때 `../../driftlens-benchmark/runs/demo/orders.sqlite`는 형제 benchmark 저장소를 가리킵니다. 실제 파일 존재를 보장하지 않습니다. 설정 파일을 다른 위치로 복사하면 DB 경로를 조정해야 합니다.

database는 SQLite 읽기 전용 연결, schema_mapping은 계약의 고정 orders 매핑, amount_unit은 integer_cents, model은 provider와 모델 ID·API 키 환경변수 이름입니다. budgets는 모델 호출·시간·SQL·요청 수 상한입니다. 과거 max_turns 키는 제거했습니다. CSV 변환은 benchmark 책임이고 단위 변환·다른 DB는 이번 범위 밖입니다.

실제 비밀 값은 저장하지 않습니다. 설정 로딩·오류 검증은 3단계, 실제 모델 호출은 4단계에서 구현합니다.
