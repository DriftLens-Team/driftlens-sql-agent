# SemAlign v2 검증 기록

이슈 [#18](https://github.com/DriftLens-Team/driftlens-sql-agent/issues/18)에 사용자의 순차 구현 승인 근거를 기록했다. 개발 변경은 dev 대상 검토용이며 main 릴리스·병합 승인을 포함하지 않는다. v1 기본값·설정·응답은 보존하고 v2를 명시적으로 선택한다. 설치 패키지 버전은 기존 개발 버전을 유지한다.

## 검증 범위

- 키 없는 단위 테스트: 설정·기간·scalar·null·반올림, 허용 SQL·읽기 전용 예산, 요청 간 상태 격리, v1 회귀.
- 독립 손계산 DB: 세전/세후 평균, 혼합 품목 포함/제외, 활성 고객 임계값, 전체 이력 신규 고객, 전주 대비 비율과 세율.
- 실제 companion CLI: benchmark의 독립 8주 자료 56건과 로컬 driftlens-data 364건을 fake provider로 생성해 전부 검수 통과.
- 실제 Upstage `solar-pro4-260806`: 7개 지표를 한 번씩 호출해 응답 7건, benchmark 검수 통과 3건·탈락 4건. 통과율 3/7은 해당 표본에만 해당한다.

실제 모델에서 평균 주문액·신규 고객은 시간대 접미사가 없는 DB 값과 `...Z` 경계 문자열 비교가 달랐다. 성장률에는 전주 이력 완전성 조건이 빠졌고, 세율은 정수 나눗셈과 세금 0의 null 처리 문제가 있었다. 실행값과 답변은 맞았지만 올바른 업무 정의를 구현하지 못한 사례다. 원본 응답을 보존했고 추가 호출로 교체하지 않았다. 이 7건은 첫 주 표본이며 drift 양성 평가나 전체 364건 실제 모델 검증을 뜻하지 않는다.

검수기와 탐지기는 SQL 의미 추출 코드를 공유하므로 통과 관측의 높은 탐지 점수는 독립 정확도 증명이 아니다. 별도 Python 참조 계산과 반례 DB를 함께 사용해 수치 우연 일치를 검사한다. 상세 집계와 재현 명령은 benchmark의 `docs/semalign-verification.md`에 기록한다.

## 실행 명령

2026-10-28 로컬 결과: 단위 테스트 55개 통과, wheel 빌드 성공. wheel의 prompt 2개와 Python 파일 컴파일을 확인했고 별도 설치 경로에서 capabilities가 agent/v2와 7개 개념을 반환했다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
.venv/Scripts/python.exe -m build --wheel
```

새 dataclass 검증 훅, CLI 진입점, 모델 교체 메서드는 호출 인터페이스에 필요하다. parse·값·답변 검증은 실행 경계와 서로 다른 검증 사례에서 재사용한다. benchmark 내부 모듈은 import하지 않는다. SQL 권한 제한은 유지하지만 OS 프로세스 격리는 제공하지 않는다.
