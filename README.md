# DriftLens SQL agent example

Python 3.11+ bounded agent loop: model chooses a JSON query action, the application
executes read-only SQLite, supplies the result, and the model chooses its answer.
This example consumes public DriftLens L3 logs and replays their SQL observations;
it is not a change-point detector or an independently evaluated text-to-SQL model.
The project description's "evaluating logs" currently means SQL-result and answer
consistency checks. Benchmark drift scoring and detection metrics are not implemented.

Keep the benchmark checkout alongside this checkout, then in PowerShell:
```powershell
$env:PYTHONPATH='../driftlens-benchmark'
python -m unittest -v
python agent.py --logs ../driftlens-benchmark/runs/demo/logs.jsonl --db ../driftlens-benchmark/runs/demo/orders.sqlite --mode fake
```
Generate the demo first using the benchmark README. Alternatively install the
benchmark package from its checkout with `python -m pip install ../driftlens-benchmark`.
The example imports its public loader, SQL tool and validator instead of duplicating them.

The fake model deterministically requests the observed SQL and reads the actual
tool result. Expected counts are 3, 2; stdout explicitly labels `mode: fake`.
Real mode uses Upstage with externally configured UPSTAGE_API_KEY and UPSTAGE_MODEL.
Run with `--mode llm` only after choosing an account-supported model. No live API
call, signup, key creation or credential storage was performed. Provider JSON-action
support and answer quality remain unverified. There is no silent fake fallback.

The tool opens the database in mode=ro, enables query_only and allows only reads
from orders and a small function allowlist. One SQL statement per call, 10k SQL
characters, 100 result rows, 100k approximate VM steps, and 5 model turns bound work.
Errors go back to the model to permit retry. Failed queries invalidate previous
observations. Answers require a successful scalar integer result and matching
numbers. Stale-definition queries remain valid; no current-policy oracle is used.
`sql_query` in agent stdout is the executed SQL; benchmark logs retain the contract's `sql` field.

Only logs.jsonl is loaded. Truth, changes, run metadata, and v2 ontology are never
included in model messages. The SQLite snapshot must contain only source orders;
do not provide private files to the agent process. L3 public SQL/definition clues
are intentionally visible. Model prompt injection resilience is not established.

Six offline tests cover actual result reading, stale SQL, recovery after a denied
write, invalid actions, turn budget, fabricated answers, failed-query invalidation,
and missing credentials. Benchmark tests cover the shared SQL restrictions.
