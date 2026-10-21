# AI 작업 지침

- 모든 협업 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다. 이 문서에 승인·브랜치·릴리스 규칙을 중복 정의하지 않는다.
- 작업 범위와 승인 근거는 해당 GitHub 이슈에서 확인한다.
- 새 구현의 기준은 [계약 v1](docs/contracts/v1/README.md)과 [검증 계획](docs/contracts/v1/validation.md)이다. 문서에 정의된 기능과 실제 구현된 기능을 구분한다.
- benchmark 내부 모듈을 새 코드에서 import하지 않는다. benchmark의 adapter 변경은 별도 작업이다.
- 요청마다 상태를 격리하고 실행에 선택된 profile 하나만 사용한다. truth·변경 일정·미래 profile을 모델 입력에 포함하지 않는다.
- 단일 에이전트 구조를 유지한다. memory/planner는 필요가 승인될 때 구현하며 빈 폴더를 만들지 않는다.
- 기본 자동 검증은 실제 LLM 키 없이 실행한다. 실제 LLM 품질을 확인하지 않았다면 미검증으로 보고한다.
- 패키지 설치 후 같은 Python 환경에서 `python -m unittest discover -s tests/unit -p "test_*.py" -v`로 현재 테스트를 실행한다. 2단계의 CLI 확인 테스트를 런타임 검증으로 보고하지 않는다.
