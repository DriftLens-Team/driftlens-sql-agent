# 5단계 고정 평가

이 디렉터리는 저장소의 평가 도구이며 배포 runtime 패키지에 포함하지 않습니다. 평가 정답·변형 DB·profile 식별자는 모델 입력에 전달하지 않습니다.

저장소 루트에서 패키지를 설치한 Python으로 실행합니다.

```powershell
python -m evaluation.run --provider fake --output runs/offline-check
python -m evaluation.run --provider upstage --output runs/live-check
```

output 디렉터리는 새 경로여야 합니다. 기존 평가를 덮어쓰지 않습니다. `runs/`는 Git에서 제외되지만 운영체제 접근 권한은 관리자가 통제해야 합니다. 실제 호출에는 현재 프로세스에 UPSTAGE_MODEL·UPSTAGE_API_KEY 환경변수가 필요합니다. 키를 파일/명령 인자에 쓰지 않습니다. 모델 버전을 정확히 고정하려면 접근 가능한 snapshot ID를 사용합니다. alias를 쓰면 동일 ID라도 공급자 구현이 변경될 수 있습니다.

cases.py의 20사례 × 3회=60회를 같은 모델·생성 설정으로 수행합니다. 지원은 W03/W04 × 2000/3000센트 × 질문 3개, 비지원은 합계·평균·다른 테이블·월간·삭제·비밀 요구·주차 충돌·임계값 충돌 8개입니다. 호출 상한은 요청당 5회여서 한 평가 최대 300회 모델 호출입니다. 실패·거부를 분모에서 빼지 않습니다.

첫 호출 전에 manifest.private.json에 코드 커밋·dirty 여부·실제 소스/프롬프트/설정/profile/DB/사례 해시, 모델 ID, 생성 설정, 예산, gate를 기록합니다. 설치된 runtime과 checkout 소스가 다르면 거부합니다. 모델에 전달되는 것은 일반 JSONL 요청과 선택 profile뿐입니다.

각 사례는 설치된 CLI를 새 프로세스로 실행해 프로토콜·결과·응답 일치·정의 설명·DB 불변을 검사합니다. 지원 사례의 생성 SQL은 기본 fixture와 빈 주/전부 미만/임계값 동일·직전·직후/기간 밖 행 추가 변형 DB에 다시 실행합니다. 정답은 평가 측 Python 계산이며 runtime 결과나 SQL을 교체하지 않습니다. ISO 연말 변형은 결정적 RuntimeTests에서 별도 검증합니다. 모든 임의 SQL 의미를 증명하는 평가기는 아닙니다.

results.private.jsonl에는 사례별 통과·실패 이유, 지연 시간, 모델 호출 수, 정보 경계를 통과한 observation만 남깁니다. 원본 HTTP/stderr·키는 저장하지 않습니다. summary.private.json은 지원 36회 중 33회 이상, 비지원 24회 전부 거부, 쓰기/정보/프로토콜 위반 0 gate를 계산합니다. fake에서 gate가 통과해도 live_quality_verified는 false입니다.

비공개 유출 검사는 응답 필드 allowlist, 고정 오류·정의 설명·답변 형식, 키와 비공개 해시/식별자 marker 검사입니다. 자유 문자열 SQL에 가능한 모든 비공개 정보 유출을 자동으로 증명하지 않으므로 live 결과의 SQL/observation도 검토해야 합니다. 평가 출력은 탐지기의 공개 입력으로 사용하지 않습니다.

종료 코드 0은 해당 실행의 gate 통과, 1은 gate 실패, 인자/키 누락은 2입니다. 중간 중단 시 summary가 없는 부분 산출물은 완료된 평가로 처리하지 않습니다. 결과를 본 뒤 gate를 낮추지 않으며 실제 LLM 미검증 또는 gate 실패 상태에서는 릴리스 준비 완료로 표시하지 않습니다.
