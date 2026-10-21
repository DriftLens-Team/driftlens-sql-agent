# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

현재 **2단계: 패키지 기반 구성** 상태인 단일 SQL 에이전트 프로젝트입니다. 기존 실험용 replay 코드는 제거했습니다. SQL 생성, 설정·profile 로딩, DB 조회, JSONL 통신은 아직 구현되지 않았습니다.

## 설치와 확인

Python 3.11 이상이 필요합니다. 저장소 루트의 PowerShell에서 실행합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/driftlens-sql-agent.exe --help
.venv/Scripts/python.exe -m driftlens_sql_agent --version
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
```

다른 운영체제에서는 `.venv/bin/`의 대응 실행 파일을 사용합니다. 패키지 확인에는 benchmark 체크아웃·API 키·런타임 외부 라이브러리가 필요하지 않습니다. 빌드 도구 설치에는 패키지 저장소 연결이 필요할 수 있습니다.

`0.1.0.dev0`은 개발 패키지 버전이며 릴리스 선언이 아닙니다. 현재 `--config`와 `--profile`을 지정한 실행은 stdout 없이 stderr에 `runtime_not_implemented`를 출력하고 코드 2로 종료합니다. 도움말·버전 출력은 JSONL 통신과 별개인 CLI 확인 기능입니다.

## 구성과 다음 단계

| 경로 | 역할 |
| --- | --- |
| `src/driftlens_sql_agent/` | 설치 가능한 패키지와 도움말·버전 진입점 |
| `pyproject.toml` | 빌드 정보, Python 요구 버전, 명령 등록 |
| `tests/unit/` | 설치된 패키지의 CLI 검증 |
| `configs/`, `profiles/` | 계약에 맞춘 후속 구현 예시. 현재 로딩하지 않음 |
| `docs/contracts/v1/` | 계약 및 후속 검증 기준 |

3단계에서 설정·SQL 접근·실행 루프, 4단계에서 모델·JSONL·CI, 5단계에서 실제 LLM 평가와 릴리스 검토를 진행합니다. 실제 benchmark adapter는 별도 작업이며 이 패키지는 drift 탐지·채점을 수행하지 않습니다.

[정리 내역](docs/migration-phase-2.md), [구현 상태](docs/README.md), [계약 v1](docs/contracts/v1/README.md), [검증 계획](docs/contracts/v1/validation.md)을 참고하세요. 협업자는 [CONTRIBUTING.md](CONTRIBUTING.md), AI 에이전트는 추가로 [AGENTS.md](AGENTS.md)를 따릅니다.

## 라이선스

[Apache-2.0](LICENSE).
