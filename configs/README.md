# 런타임 설정 예시

[`runtime.example.json`](runtime.example.json)을 복사하고 `database.path`를 사용할 SQLite DB 경로로 수정합니다. CLI는 시작 시 설정을 검증합니다.

## 설정 항목

| 항목 | 설정 방법 |
| --- | --- |
| `database` | `kind`는 `sqlite`, `read_only`는 `true`로 지정합니다. `path`는 존재하는 SQLite DB 파일을 가리켜야 합니다. |
| `schema_mapping` | 예시의 `orders` 테이블과 `order_id`, `ordered_at`, `order_total_cents` 열 매핑을 유지합니다. 현재 구현은 이 고정 매핑만 지원합니다. |
| `amount_unit` | `integer_cents`를 사용합니다. 금액은 정수 센트 단위입니다. |
| `model` | `provider`는 `upstage` 또는 `fake`입니다. `id_env`와 `api_key_env`에는 모델 ID와 API 키를 읽을 환경변수 이름을 지정합니다. |
| `budgets` | 모델 호출·재시도 횟수, 요청·모델·SQL 시간, SQL 실행량·문자 수·결과 행 수, 요청 수를 제한합니다. 생략한 항목은 기본값을 사용하며 예시의 상한보다 높게 설정할 수 없습니다. |

DB 상대 경로는 **설정 파일이 있는 디렉터리**를 기준으로 해석합니다. 예시의 `../../driftlens-benchmark/runs/demo/orders.sqlite`는 형제 benchmark 저장소의 파일을 가리킵니다. 해당 파일이 없다면 사용 가능한 DB 경로로 변경해야 합니다. 설정 파일을 다른 위치로 복사할 때도 상대 경로를 확인하세요.

업무 정의와 임계값은 런타임 설정과 별도로 `--profile`에서 선택합니다. 지원하는 DB 스키마와 설정 값의 자세한 조건은 [계약 v1](../docs/contracts/v1/README.md)을 참고하세요.

## 모델과 실행

실제 모델을 사용하려면 `model.provider`를 `upstage`로 지정하고, 실행 환경에 `UPSTAGE_MODEL`과 `UPSTAGE_API_KEY`를 설정합니다. 환경변수 이름을 변경했다면 `id_env`와 `api_key_env`도 맞춰야 합니다. API 키 자체를 JSON 설정에 저장하지 않습니다.

API 호출 없이 실행 흐름을 확인하려면 `model.provider`를 `fake`로 지정합니다. 이 모델은 정해진 테스트 질문만 지원합니다.

Python 3.11 이상에서 패키지를 설치한 뒤, 수정한 설정 파일과 profile을 지정해 실행합니다.

```shell
python -m pip install -e .
python -m driftlens_sql_agent --config configs/runtime.example.json --profile profiles/v1/profile.example.json --protocol-version v1
```

일반 CLI는 `.env`를 자동으로 읽지 않습니다. F5와 `python scripts/start.py`는 `.env`와 실행 환경을 확인해 모델을 자동 선택합니다. `runs/local-debug/runtime.json`을 바탕으로 실행용 임시 설정을 만들며 기존 DB와 설정 파일은 보존합니다. 설치와 자동 선택 조건은 [빠른 시작](../README.ko.md)을 참고하세요.

- [JSONL 입력과 실행 안내](../docs/running.md)
- [VS Code 디버깅 안내](../docs/debugging.md)
