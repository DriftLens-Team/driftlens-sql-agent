# 공통 엔진 계획
runtime.py에 공통 질의·답변 흐름, sql_access.py에 SQLite 읽기 전용 조회와 DB 교체 경계, transport.py에 JSONL 입출력을 모은다. 모두 주석만 있는 향후 파일이다. 함수·클래스를 세분화하거나 기존 agent.py를 이동하지 않는다. SQLite 우선이며 다른 DB는 연결 설정·SQL 방언·결과 형태를 이 경계에서 교체할 계획만 둔다.
