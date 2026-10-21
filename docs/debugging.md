# VS Code에서 실제 CLI 디버깅

저장소 루트 폴더를 VS Code로 엽니다. Python 및 Python Debugger 확장을 설치하고 Python 3.11 이상으로 가상환경과 패키지를 준비합니다.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
```

macOS/Linux는 설치 명령의 Python 경로를 `.venv/bin/python`으로 바꿉니다. 이미 가상환경과 editable 설치가 있으면 다시 만들 필요가 없습니다.

루트의 Git 제외 `.env`에 `UPSTAGE_MODEL`과 `UPSTAGE_API_KEY`를 설정합니다. VS Code가 디버그 프로세스에 전달하며 CLI 자체가 `.env`를 자동 로딩하는 것은 아닙니다. 값은 커밋하지 않습니다.

## F5 실행

1. 실행 및 디버그(Ctrl+Shift+D)에서 `SQL agent - 실제 CLI (Upstage)`를 선택합니다.
2. 실제 `src/driftlens_sql_agent/` 코드 줄 번호 왼쪽에 중단점을 겁니다.
3. F5를 누르면 준비 작업이 `runs/local-debug/orders.sqlite`와 `runtime.json`을 없는 경우에만 생성한 뒤 실제 CLI 모듈을 실행합니다. DB는 합성 데이터이며 기존 파일은 덮어쓰지 않습니다. 기존 로컬 DB가 있으면 조회 결과는 그 내용에 따릅니다.
4. 통합 터미널에 아래 JSON을 한 줄로 입력하고 Enter를 누릅니다. Debug Console에 입력하지 않습니다. 질문 입력 시 실제 API 호출과 비용이 발생할 수 있습니다.

```json
{"request_id":"debug-1","request":"이번 주 대형 주문은 몇 건인가요?","period":"2025-W03","timestamp":"2025-01-19T23:59:59Z"}
```

새로 만든 합성 DB의 v1(2000센트 이상) 예상 건수는 2입니다. 같은 프로세스에서 다시 질문할 때는 request_id를 바꿉니다. API 키 없이 실행하려면 로컬 config의 `model.provider`를 `fake`로 설정합니다. Upstage를 사용하려면 `upstage`로 설정합니다. 기존 config는 F5 실행 시에도 보존됩니다.

실제 DB를 사용하려면 `runs/local-debug/runtime.json`의 database.path를 수정합니다. 상대 경로 기준은 config 파일 디렉터리입니다. profile은 launch.json의 `--profile` 인자로 선택합니다. 기본은 v1입니다.

## 중단점과 변수

| 위치 | 확인 대상 |
| --- | --- |
| cli.py: `runtime = Runtime(...)` | 초기 설정·DB 검증. 비밀값이 있는 설정 전체를 공유하지 않기 |
| runtime.py: `request = Request.parse(obj)` | 입력 obj, 다음 줄 실행 후 request |
| models.py: `value = model.generate(...)` 다음 줄 | 모델 응답 value, 자식 프로세스 호출 스택 |
| runtime.py: `value = count_value(result)` | action의 SQL, result의 rows |
| runtime.py: `answer = answer_value(...)` | action의 답변, observation의 최신 관측값 |

중단점은 해당 줄을 실행하기 전에 멈춥니다. VARIABLES에서 펼치거나 변수 위에 마우스를 올려 확인합니다. Debug Console은 현재 선택한 호출 스택 프레임 기준입니다. subprocess 디버깅을 켰으므로 부모/모델 자식 프로세스 중 올바른 프레임을 선택합니다.

- F10: 한 줄 실행, F11: 함수 진입, Shift+F11: 호출자로 복귀
- F5: 다음 중단점, Shift+F5: 종료
- BREAKPOINTS의 Raised Exceptions: 처리되는 예외까지 발생 위치에서 정지. 평소에는 꺼 두고 오류 분석 시 사용합니다.

## 시간 제한

디버깅 중에도 모델 20초·전체 요청 60초·SQL 2초 기본 제한은 유지됩니다. 자식 프로세스에서 멈춘 동안 부모 시간이 흐를 수 있고, 부모만 멈춰도 재개 시 deadline을 초과할 수 있습니다. SQL 내부에 오래 멈추면 SQL timeout이 발생할 수 있습니다. 이 설정은 시간을 정지하거나 제한을 해제하지 않습니다. 초기에는 SQL 호출은 F10으로 넘기고 결과를 확인하세요.

