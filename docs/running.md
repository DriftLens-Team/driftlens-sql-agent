# JSONL 실행 안내

VS Code에서 F5로 실제 CLI를 실행하려면 [디버깅 설정 안내](debugging.md)를 따릅니다.

DB 생성과 모델 자동 선택을 포함한 터미널 빠른 시작은 `.venv/Scripts/python.exe scripts/start.py`입니다(macOS/Linux: `.venv/bin/python scripts/start.py`). 이 스크립트는 루트 `.env`를 읽고 실행 환경의 값을 우선합니다. [README](../README.ko.md)의 설치·설정·질문 예시를 따르세요. 아래 일반 CLI는 config와 환경변수를 직접 지정하는 방식입니다.

Python 3.11 이상에서 `python -m pip install -e .`로 설치합니다. config의 DB 경로를 실제 불변 SQLite 스냅샷 위치로 수정하고 profile 하나를 선택합니다. DB 경로는 config 파일 기준입니다.

```powershell
python -m driftlens_sql_agent --config configs/runtime.example.json --profile profiles/v1/profile.example.json --protocol-version v1
```

stdin에 [계약](contracts/v1/README.md)의 UTF-8 JSONL을 전달하면 응답을 한 줄씩 즉시 flush합니다. PowerShell의 파이프 인코딩에 의존하기보다 부모 프로그램이 UTF-8 bytes를 전달하도록 권장합니다. 정상 EOF는 0, 설정/프로토콜 실패는 2, 내부/출력 실패는 1입니다. stderr는 비공개 메타데이터 진단이며 공개 로그에 합치지 않습니다.

오프라인 실행은 복사한 config에서 `model.provider`를 `fake`로 지정합니다. fake는 검증용 질문 3개만 인식합니다. 실제 호출은 `upstage`와 config에 지정한 환경변수 `UPSTAGE_MODEL`, `UPSTAGE_API_KEY`를 설정합니다. 키 값은 파일·커밋·진단에 기록하지 않습니다. 환경변수 설정 후 필요하면 실행 터미널/앱을 다시 열어 새 환경을 상속시킵니다.

모델 ID는 사용자가 접근 가능한 모델의 명시적 환경변수 값이며 코드에서 추측하거나 대체하지 않습니다. 일반 CLI 자체는 `.env`를 자동 탐색·로딩하지 않습니다. 운영 HTTP 목적지는 고정된 `https://api.upstage.ai/v1/chat/completions`입니다. 리다이렉트는 따라가지 않습니다. 로컬 HTTP 주소 주입은 모의 테스트 코드에서만 사용합니다.

[Upstage 공식 API](https://console.upstage.ai/api/chat)를 2026-10-21 확인했습니다. 생성 설정은 temperature=0, max_tokens=1024, stream=false, response_format=json_object로 고정합니다. 공급자 HTTP는 재시도하지 않고 runtime이 전체 호출·재시도 예산을 관리합니다. 요청별 프로세스가 느린 응답도 deadline에 종료합니다. 모델별 JSON 모드/파라미터 지원과 실제 응답 품질은 live 평가에서 확인해야 합니다.

HTTP 401/403은 인증 실패, 408은 timeout, 연결 오류·429·5xx는 제한된 재시도 대상입니다. 그 외 HTTP 실패는 재시도하지 않습니다. Retry-After가 1초보다 길면 대기하지 않습니다. HTTP 응답 본문을 최대 65,536 bytes까지만 허용하며 그 안에서 completion JSON의 action을 검증합니다.

실제 benchmark adapter는 별도 저장소의 후속 작업입니다. 여기의 모의 부모 테스트가 실제 연동 완료를 뜻하지 않습니다. [검증 기록](verification.md)을 확인하세요.
