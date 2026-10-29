# DriftLens SQL Agent

명시적으로 선택하는 [SemAlign agent/v2](docs/contracts/v2/README.md)는 7개 지표, JOIN·과거 이력·주간 기간과 null·비율 결과를 지원합니다. 기본값은 v1입니다. 실제 모델 소규모 검증에서 확인한 제한은 [v2 검증 기록](docs/contracts/v2/validation.md)에 정리했습니다.

[English](README.md) | [한국어](README.ko.md)

SQLite에서 주간 대형 주문 건수를 조회하는 읽기 전용 SQL 에이전트입니다. `orders` 스키마, 정수 센트, UTC 주간, 선택한 업무 정의 하나를 지원합니다. drift 탐지·채점과 실제 benchmark adapter는 별도 범위입니다.

## 빠른 시작

### 1. 설치

Python 3.11 이상이 필요합니다. 저장소 루트에서 실행합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
```

macOS/Linux에서는 아래 명령의 `.venv/Scripts/python.exe` 대신 `.venv/bin/python`을 사용합니다.

### 2. 모델 설정 — 선택 사항

실제 모델을 사용하려면 루트에 `.env` 파일을 만듭니다.

```dotenv
UPSTAGE_MODEL=사용가능한-모델-ID
UPSTAGE_API_KEY=발급받은-API-키
```

두 값을 실제 값으로 바꿉니다. 비밀값은 커밋하지 않습니다. API 키 없이 예시를 실행하려면 두 설정을 모두 생략합니다. 실행 환경에 이미 지정된 변수는 `.env`보다 우선하며 빈 값도 명시적 설정으로 취급합니다.

| 최종 설정 상태 | 동작 |
| --- | --- |
| 두 변수 모두 미지정 | 오프라인 `fake` 모델. 정해진 예시 질문만 지원 |
| 두 값 모두 유효한 비어 있지 않은 문자열 | 실제 Upstage 모델. API 호출 비용이 발생할 수 있음 |
| 일부 누락 또는 빈 값 | 시작 오류, fake로 전환하지 않음 |
| 인증·네트워크·모델 호출 실패 | 오류 반환, fake로 전환하지 않음 |

빠른 시작 로더는 `KEY=VALUE`, 빈 줄, 줄 전체 `#` 주석, 작은따옴표/큰따옴표로 감싼 값을 지원합니다. 변수 치환·명령 실행·인라인 주석·여러 줄 값은 지원하지 않습니다. 잘못된 줄과 모델 설정 중복은 거부하며, 다른 정상 형식의 변수는 무시합니다.

### 3. F5 또는 터미널로 실행

**VS Code:** 저장소 루트를 열고 권장 Python·Python Debugger 확장을 설치합니다. **SQL agent - Quick start (auto)**를 선택하고 **F5**를 누릅니다.

**터미널:** 같은 실행기를 직접 호출합니다.

```powershell
.venv/Scripts/python.exe scripts/start.py
```

두 방식 모두 `runs/local-debug/orders.sqlite` 합성 DB와 `runtime.json`이 없을 때 생성한 뒤 실제 CLI를 실행합니다. 기존 DB/config는 보존됩니다. 자동 선택은 실행용 임시 config에만 적용하며 저장된 provider를 수정하지 않습니다. 선택 모드와 DB 경로는 stderr에 표시하고 비밀값은 출력하지 않습니다. 기본 profile은 `profiles/v1/profile.example.json`의 2000센트 기준입니다.

### 4. 질문 입력과 결과 확인

실행 중인 터미널에 아래 JSON 한 줄을 붙여넣고 Enter를 누릅니다.

```json
{"request_id":"demo-1","request":"이번 주 대형 주문은 몇 건인가요?","period":"2025-W03","timestamp":"2025-01-19T23:59:59Z"}
```

성공 응답은 `status: "ok"`이며 `observation`에 SQL·답변·건수가 들어 있습니다. 새 합성 DB의 예상 결과는 **2건**이며 기존 DB가 있으면 결과가 다를 수 있습니다. 중간 `stage` 줄은 stderr 진단, 최종 응답은 stdout JSONL입니다. 추가 요청은 request_id를 바꿉니다. F5 종료는 Shift+F5, 터미널 실행 종료는 Ctrl+C입니다.

## config를 명시한 직접 실행

자신의 DB/profile과 모델을 지정하려면 `configs/runtime.example.json`을 복사·수정하고, Upstage 사용 시 자격 증명을 실행 환경변수에 설정합니다.

```powershell
.venv/Scripts/python.exe -m driftlens_sql_agent --config configs/runtime.example.json --profile profiles/v1/profile.example.json --protocol-version v1
```

이 명령은 config의 provider를 사용하며 `.env` 로딩·모델 자동 선택을 하지 않습니다. DB 상대 경로는 config 파일 기준입니다. [설정 안내](configs/README.md), [JSONL 실행 안내](docs/running.md)를 참고하세요.

## 개발과 한계

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
```

중단점에서도 모델·요청·SQL 시간 제한은 유지됩니다. [디버깅](docs/debugging.md), [계약](docs/contracts/v1/README.md), [검증 기록](docs/verification.md)을 참고하세요. 고정 실제 평가에서 지원 36/36, 미지원 거부 24/24를 통과했지만 독립 미공개 평가나 임의 질문의 정확성을 보장하지 않습니다. 센트 충돌 검사도 모든 자연어 표현을 처리하지 않습니다.

협업 절차는 [CONTRIBUTING.md](CONTRIBUTING.md), 라이선스는 [Apache-2.0](LICENSE)입니다.
