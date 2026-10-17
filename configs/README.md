# 런타임 설정 예시
runtime.example.json은 현재 agent.py에서 읽지 않는 미래 설정이다. DB 경로는 저장소 루트 기준의 합성 위치 예시이며 파일 존재를 보장하지 않는다. database는 DB 종류·연결 경로·읽기 전용 여부, schema_mapping은 논리 필드에서 SQLite 컬럼으로의 매핑, amount_unit은 정수 센트, model은 외부 환경변수 이름, max_turns는 실행 예산이다. 키와 모델 ID 실제 값은 저장하지 않는다. 원본 CSV id/order_total에서 SQLite order_id/order_total_cents로의 변환은 benchmark의 기존 생성기 책임이다. 다른 DB는 engine/sql_access.py의 교체 경계만 계획한다.
