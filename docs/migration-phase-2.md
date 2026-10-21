# 2단계 정리 내역

이슈 [#1](https://github.com/DriftLens-Team/driftlens-sql-agent/issues/1)의 승인된 범위에 따라 기존 실험 코드를 제거하고 패키지 기반을 구성합니다. 이전 구현은 Git 이력의 `22a495f`에서 확인할 수 있습니다. 호환 shim이나 별도 legacy 복사본은 두지 않습니다.

| 기존 항목 | 조치와 이유 |
| --- | --- |
| `agent.py` | 제거. benchmark 내부 import, replay, fake/live 모델과 루프가 섞인 실험 구현 |
| `test_agent.py` | 제거. 제거된 replay 구현 전용 테스트. 유효한 동작 요구는 계약 검증 계획으로 보존 |
| `engine/` | 주석 전용 Python 파일과 미래 설계 설명 제거. 실제 구현 시 src 패키지에 모듈 추가 |
| `prompts/README.md` | 제거. 공통 지시 원칙은 계약으로 통합. 실제 프롬프트는 모델 구현 단계에서 패키지 내부에 추가 |
| `docs/assets/data-flow.png` | 제거. 과거 CSV→benchmark→replay 흐름으로 현재 실행 방법을 오해할 수 있음 |
| `configs/runtime.example.json` | DB 경로를 config 디렉터리 기준으로 수정하고 max_turns를 계약의 budgets로 교체 |
| `profiles/` | 합성 업무 정의 예시는 유지. 실제 로딩 미구현 상태를 명시 |
| README·docs·tests 설명 | 실행 불가능한 과거 명령 제거, 현재 설치·테스트와 후속 구현 상태로 대체 |

## 사용 영향

- `python agent.py --logs ... --db ...`와 PYTHONPATH를 통한 benchmark 내부 import 방식은 더 이상 지원하지 않습니다.
- 설치 후 `driftlens-sql-agent --help`, `--version` 또는 `python -m driftlens_sql_agent`로 진입점을 확인합니다.
- 런타임 요청은 현재 명시적으로 실패합니다. 기존 실험 실행 기능이 필요하면 과거 커밋을 별도 checkout하여 확인해야 합니다.
- 설정·SQL 도구·상태·재시도·답변 검증 요구는 제거하지 않았으며 [계약](contracts/v1/README.md)과 [검증 계획](contracts/v1/validation.md)에 따라 3단계 이후 재구현합니다.
- 설치/CLI 검증은 실제 SQL 에이전트 품질 검증이 아닙니다. 모델 호출·DB 입력·JSONL 처리는 아직 하지 않습니다.
