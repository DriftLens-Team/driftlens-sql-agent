# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

Contributors: see [CONTRIBUTING.md](CONTRIBUTING.md). The approved redesign starts with the [v1 agent contract](docs/contracts/v1/README.md) and [validation plan](docs/contracts/v1/validation.md) (Korean); these describe the planned implementation, not the current replay runtime below.

A bounded SQL replay agent for [DriftLens Benchmark](https://github.com/DriftLens-Team/driftlens-benchmark). It reads public L3 logs, queries a source-only SQLite snapshot, and checks that its Korean answer agrees with the executed SQL result.

## Features

- A JSON-action loop: request a query, observe the result, then answer.
- A deterministic fake model for offline demonstrations and an optional Upstage model.
- Read-only queries with SQL length, row, execution, and turn budgets.
- Answer validation against a successful scalar integer observation; failed queries invalidate earlier observations.

This is a replay example, not an independently evaluated text-to-SQL model or a drift detector.

## Requirements and quick start

Python 3.11 or later and a sibling checkout of DriftLens Benchmark are required:

```text
driftlens-benchmark/
driftlens-sql-agent/
```

First generate `runs/demo` using the [benchmark quick start](https://github.com/DriftLens-Team/driftlens-benchmark#requirements-and-quick-start). Then run these commands from the agent repository root in PowerShell:

```powershell
$env:PYTHONPATH='../driftlens-benchmark'
python -m unittest -v
python agent.py --logs ../driftlens-benchmark/runs/demo/logs.jsonl --db ../driftlens-benchmark/runs/demo/orders.sqlite --mode fake
```

Alternatively, install the benchmark's shared modules from its local checkout with `python -m pip install ../driftlens-benchmark` instead of setting `PYTHONPATH`.

For the benchmark fixture, expected counts are **3 and 2**. Fake mode uses the observed SQL and actual tool results without network requests; output is explicitly marked `mode: fake`.

For live mode, configure `UPSTAGE_API_KEY` and `UPSTAGE_MODEL` externally and replace `--mode fake` with `--mode llm`. Choose an account-supported model. There is no silent fallback to fake mode. Live JSON-action compatibility and answer quality remain unverified. Never store credentials in the repository.

## Use logs generated from an external CSV

The agent does not accept CSV directly. Start with the benchmark's [external CSV guide](https://github.com/DriftLens-Team/driftlens-benchmark/blob/main/README.md#use-the-external-csv): it identifies the pinned [dbt-labs/jaffle-shop source](https://github.com/dbt-labs/jaffle-shop/blob/5beb145b00f5465ec759cfcdd9745e858818cf95/seeds/jaffle-data/raw_orders.csv), download path, required columns, cents/UTC conventions, source hash, and unconfirmed upstream data license. The CSV is not redistributed here.

![External CSV flows through the benchmark into public logs and SQLite for the agent; private labels remain separate](docs/assets/data-flow.png)

*Setup diagram, not an execution screenshot. Keep both repositories beside each other.*

1. Save the raw CSV as `driftlens-benchmark/data/raw_orders.csv` following the benchmark guide.
2. Generate a new run at `driftlens-benchmark/runs/jaffle-demo/` using that guide's existing CLI.
3. From the **agent repository root**, pass the public log and snapshot from the same run:

```powershell
$env:PYTHONPATH='../driftlens-benchmark'
python agent.py --logs ../driftlens-benchmark/runs/jaffle-demo/logs.jsonl --db ../driftlens-benchmark/runs/jaffle-demo/orders.sqlite --mode fake
```

Each successful replay emits one current-format agent JSON record. Do not expect the fixture's 3 and 2 counts for external data; end-to-end execution on that source remains unverified. Keep `truth.jsonl`, `run.private.json`, and `failures.private.jsonl` out of agent inputs.

If imports fail, check the sibling layout and `PYTHONPATH`. If files cannot be opened, confirm generation succeeded and both paths point to the same run. For source column, unit, download, or date-range errors, use the benchmark guide's troubleshooting table.

## Inputs, outputs, and safeguards

`--logs` accepts only a file named `logs.jsonl` with the benchmark's exact public L3 fields. `--db` points to the source-only SQLite snapshot containing `orders(order_id, ordered_at, order_total_cents)`.

Standard output contains one JSON object per successful replay with:

```text
log_id, mode, sql_query, reported_value, answer_text
```

This is the current agent output, not the benchmark's ten-field public log or the planned request/response protocol. `sql_query` records the executed SQL; the benchmark uses `sql`.

The shared SQL tool opens SQLite with `mode=ro` and `query_only`, permits reads from `orders` and a small function allowlist, and limits each call to one statement, 10,000 SQL characters, 100 rows, and approximately 100,000 VM steps. The agent loop allows up to five model turns. Query errors return to the model for retry; a valid answer requires a successful nonnegative integer count and matching answer numbers.

The supplied SQL may use an older business definition. Its result remains a valid observation rather than being replaced with a current-policy count. Do not give the agent truth, change schedules, private run metadata, or future ontology files. L3 SQL and definition clues are intentionally visible. Prompt-injection resilience and complete semantic-leakage prevention are not established.

## Repository structure

| Path | Role |
| --- | --- |
| `agent.py` | Current CLI, fake/live models, and bounded replay loop |
| `test_agent.py` | Offline replay and failure-handling tests |
| `engine/` | Comment-only placeholders for a common runtime, SQL access, and JSONL transport |
| `profiles/v1/`, `profiles/v2/` | Planned business-definition configuration examples |
| `configs/`, `prompts/` | Runtime configuration examples and prompt design notes |
| `docs/`, `tests/` | Architecture and future test scope |

See the [architecture guide (Korean)](docs/README.md) for version tracking and information boundaries.

## Current status and roadmap

The current agent imports `driftlens`, `public_logs`, and `sql_tool` from the benchmark. Offline tests cover result reading, stale SQL, query recovery, action validation, answer consistency, and failure handling.

Independent SQL generation, a profile-configured common engine, and a separate-process JSONL connection are not implemented. The planned connection will remove cross-repository internal imports; configuration examples are not loaded by `agent.py`. SQLite is the only implemented database backend. Drift detection and scoring belong to the benchmark roadmap.

## License

[Apache License 2.0](LICENSE)
