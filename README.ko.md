# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

[DriftLens Benchmark](https://github.com/DriftLens-Team/driftlens-benchmark)의 SQL을 재실행하는 에이전트입니다. 공개 L3 로그를 읽고 원본 데이터만 담긴 SQLite 스냅샷을 조회한 뒤, 한국어 답변이 실제 SQL 결과와 일치하는지 검사합니다.

## 주요 기능

- 쿼리 요청 → 결과 확인 → 답변으로 이어지는 JSON action 루프
- 오프라인 시연용 결정적 fake 모델과 선택적인 Upstage 모델
- SQL 길이·결과 행 수·실행량·모델 턴 수를 제한한 읽기 전용 조회
- 성공한 정수 단일값 관측에 근거한 답변 검증과 쿼리 실패 시 이전 관측 무효화

독립적인 text-to-SQL 성능을 평가한 모델이나 드리프트 탐지기가 아닌 SQL replay 예제입니다.

## 요구사항과 시작하기

Python 3.11 이상과 형제 디렉터리에 있는 DriftLens Benchmark 체크아웃이 필요합니다.

```text
driftlens-benchmark/
driftlens-sql-agent/
```

먼저 [benchmark 시작 안내](https://github.com/DriftLens-Team/driftlens-benchmark/blob/main/README.ko.md#요구사항과-시작하기)에 따라 `runs/demo`를 생성합니다. 그다음 agent 저장소 루트에서 PowerShell로 실행합니다.

```powershell
$env:PYTHONPATH='../driftlens-benchmark'
python -m unittest -v
python agent.py --logs ../driftlens-benchmark/runs/demo/logs.jsonl --db ../driftlens-benchmark/runs/demo/orders.sqlite --mode fake
```

`PYTHONPATH` 설정 대신 `python -m pip install ../driftlens-benchmark`로 로컬 benchmark 체크아웃의 공통 모듈을 설치할 수도 있습니다.

benchmark fixture의 예상 결과는 **3건과 2건**입니다. fake 모드는 네트워크 요청 없이 관측된 SQL과 실제 도구 결과를 사용하며, 출력에 `mode: fake`를 명시합니다.

실제 모델을 사용하려면 `UPSTAGE_API_KEY`와 `UPSTAGE_MODEL`을 외부에서 설정하고 `--mode fake`를 `--mode llm`으로 바꿉니다. 계정에서 지원하는 모델을 선택해야 합니다. 실패 시 fake 모드로 자동 대체하지 않습니다. 실제 모델의 JSON action 호환성과 답변 품질은 아직 검증되지 않았습니다. 자격정보를 저장소에 보관하지 마세요.

## 외부 CSV에서 생성한 로그 사용하기

agent는 CSV를 직접 입력받지 않습니다. 먼저 benchmark의 [외부 CSV 안내](https://github.com/DriftLens-Team/driftlens-benchmark/blob/main/README.ko.md#외부-csv-사용하기)를 따르세요. 고정된 [dbt-labs/jaffle-shop 원본](https://github.com/dbt-labs/jaffle-shop/blob/5beb145b00f5465ec759cfcdd9745e858818cf95/seeds/jaffle-data/raw_orders.csv), 다운로드 경로, 필수 컬럼, 센트·UTC 규칙, 원본 해시와 미확인 상태인 데이터 라이선스를 설명합니다. 이 저장소에는 해당 CSV를 재배포하지 않습니다.

![외부 CSV를 benchmark가 공개 로그와 SQLite로 만들고 agent가 사용하며 비공개 정답은 분리되는 흐름](docs/assets/data-flow.png)

*실행 화면이 아닌 설정 안내도입니다. 두 저장소는 형제 디렉터리에 배치하세요.*

1. benchmark 안내에 따라 원본 CSV를 `driftlens-benchmark/data/raw_orders.csv`에 저장합니다.
2. 안내된 기존 CLI로 `driftlens-benchmark/runs/jaffle-demo/`에 새 실행 결과를 생성합니다.
3. **agent 저장소 루트**에서 같은 실행 결과의 공개 로그와 스냅샷을 지정합니다.

```powershell
$env:PYTHONPATH='../driftlens-benchmark'
python agent.py --logs ../driftlens-benchmark/runs/jaffle-demo/logs.jsonl --db ../driftlens-benchmark/runs/jaffle-demo/orders.sqlite --mode fake
```

재실행에 성공할 때마다 현재 agent 형식의 JSON 레코드를 하나씩 출력합니다. 외부 데이터에서 fixture의 3건·2건을 기대하면 안 되며, 해당 원본을 사용한 전체 연동 실행은 아직 검증되지 않았습니다. `truth.jsonl`, `run.private.json`, `failures.private.jsonl`은 agent 입력에서 제외하세요.

import가 실패하면 형제 디렉터리 배치와 `PYTHONPATH`를 확인하세요. 파일을 열지 못하면 생성이 성공했는지와 두 경로가 같은 실행 결과를 가리키는지 확인하세요. 원본 컬럼·단위·다운로드·날짜 범위 오류는 benchmark 안내의 오류 해결 표를 참고하세요.

## 입력·출력과 실행 제한

`--logs`는 benchmark의 공개 L3 필드와 정확히 일치하는 `logs.jsonl` 파일만 받습니다. `--db`는 `orders(order_id, ordered_at, order_total_cents)`를 포함한 원본 데이터 전용 SQLite 스냅샷 경로입니다.

재실행에 성공하면 표준 출력에 다음 필드의 JSON 객체를 한 줄씩 출력합니다.

```text
log_id, mode, sql_query, reported_value, answer_text
```

이는 현재 agent의 출력 형식이며 benchmark의 공개 10필드 로그나 계획된 요청·응답 프로토콜과 다릅니다. `sql_query`는 실제 실행한 SQL이고, benchmark에서는 `sql`이라는 필드명을 사용합니다.

공통 SQL 도구는 SQLite를 `mode=ro`와 `query_only`로 열고, `orders` 읽기와 제한된 함수만 허용합니다. 호출당 SQL 문장 1개, SQL 길이 10,000자, 결과 100행, 약 100,000 VM step으로 제한하며 모델 루프는 최대 5턴입니다. 쿼리 오류는 재시도할 수 있도록 모델에 전달합니다. 유효한 답변에는 성공한 음이 아닌 정수 건수 관측과 일치하는 답변 숫자가 필요합니다.

전달받은 SQL이 이전 업무 정의를 사용하더라도 유효한 관측으로 유지하며 최신 정의의 건수로 바꾸지 않습니다. 정답·변경 일정·비공개 실행 메타데이터·미래 온톨로지 파일을 agent에 제공하지 마세요. L3의 SQL과 정의 단서는 의도적으로 공개됩니다. 프롬프트 주입 방어와 완전한 의미적 누출 방지는 검증되지 않았습니다.

## 저장소 구조

| 경로 | 역할 |
| --- | --- |
| `agent.py` | 현재 CLI, fake/live 모델, 제한된 replay 루프 |
| `test_agent.py` | 오프라인 재실행·실패 처리 테스트 |
| `engine/` | 공통 실행·SQL 접근·JSONL 통신의 주석 전용 예정 파일 |
| `profiles/v1/`, `profiles/v2/` | 향후 업무 정의 설정 예시 |
| `configs/`, `prompts/` | 런타임 설정 예시와 프롬프트 설계 설명 |
| `docs/`, `tests/` | 아키텍처와 향후 테스트 범위 |

버전 기록과 정보 경계는 [아키텍처 안내](docs/README.md)를 참고하세요.

## 현재 상태와 로드맵

현재 agent는 benchmark의 `driftlens`, `public_logs`, `sql_tool`을 import합니다. 오프라인 테스트는 결과 읽기·이전 정의 SQL·쿼리 복구·action 검증·답변 일관성·실패 처리를 다룹니다.

독립 SQL 생성, profile 설정 기반 공통 엔진, 별도 프로세스 JSONL 연결은 아직 구현되지 않았습니다. 계획된 연결 방식에서는 저장소 간 내부 import를 제거합니다. `agent.py`는 설정 예시 파일을 읽지 않습니다. 구현된 DB는 SQLite뿐이며, 드리프트 탐지와 채점은 benchmark의 로드맵에 속합니다.

## 라이선스

[Apache License 2.0](LICENSE)
