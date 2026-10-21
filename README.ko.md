# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

현재 **4단계: 모델·JSONL 연결** 상태인 단일 SQL 에이전트 프로젝트입니다. 기존 실험용 replay 코드는 제거했습니다. 설정·profile 검증, 읽기 전용 SQLite, 요청 격리, 실행 예산과 답변 검증을 구현했습니다. fake 모델로 오프라인 실행을 검증하며 Upstage HTTP·JSONL 통신을 구현했습니다. 실제 모델 품질은 별도 평가 대상입니다.

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

`0.1.0.dev0`은 개발 패키지 버전이며 릴리스 선언이 아닙니다. `--config`와 `--profile`을 지정하여 UTF-8 JSONL을 처리합니다. [실행 안내](docs/running.md), [Python API](docs/runtime-phase-3.md), [요건별 검증 기록](docs/verification.md)을 참고하세요. 도움말·버전 출력은 JSONL 통신과 별개인 CLI 확인 기능입니다.

## 구성과 다음 단계

| 경로 | 역할 |
| --- | --- |
| `src/driftlens_sql_agent/` | 설정·SQL 도구·실행 루프·모델 경계와 CLI |
| `pyproject.toml` | 빌드 정보, Python 요구 버전, 명령 등록 |
| `tests/unit/` | CLI·설정·임시 SQLite·격리 모델 검증 |
| `configs/`, `profiles/` | Python API로 로딩하는 v1 설정 예시 |
| `docs/contracts/v1/` | 계약 및 후속 검증 기준 |

5단계에서 실제 LLM 평가와 릴리스 검토를 진행합니다. 실제 benchmark adapter는 별도 작업이며 이 패키지는 drift 탐지·채점을 수행하지 않습니다.

[정리 내역](docs/migration-phase-2.md), [구현 상태](docs/README.md), [계약 v1](docs/contracts/v1/README.md), [검증 계획](docs/contracts/v1/validation.md)을 참고하세요. 협업자는 [CONTRIBUTING.md](CONTRIBUTING.md), AI 에이전트는 추가로 [AGENTS.md](AGENTS.md)를 따릅니다.

## 라이선스

[Apache-2.0](LICENSE).

5단계 평가 도구와 오프라인 리허설을 준비했습니다. 실제 품질은 환경변수 설정 후 평가합니다. [평가 안내](evaluation/README.md)와 [검증 기록](docs/verification.md)을 참고하세요.
