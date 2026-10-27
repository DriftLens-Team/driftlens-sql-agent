# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

A bounded, read-only SQL agent that answers weekly large-order counts from SQLite. It supports the `orders` schema, integer cents, UTC weeks and one selected business profile. It does not perform drift detection; the benchmark adapter is separate.

The opt-in [SemAlign agent/v2](docs/contracts/v2/README.md) also supports seven metrics, joins, historical weekly windows and nullable scalar results. The default remains v1. See the [v2 verification record](docs/contracts/v2/validation.md), including the limits of the real-model smoke test.

## Quick start

### 1. Install

Requires Python 3.11+. In the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
```

On macOS/Linux use `.venv/bin/python` instead of `.venv/Scripts/python.exe` below.

### 2. Optional model settings

For a real model, create a `.env` file in the repository root:

```dotenv
UPSTAGE_MODEL=your-accessible-model-id
UPSTAGE_API_KEY=your-api-key
```

Replace both placeholders with valid values. Do not commit credentials. To try the example without an API key, omit both settings. Existing process environment variables override `.env`, including explicitly empty values.

| Effective settings | Behavior |
| --- | --- |
| Neither variable specified | Offline `fake` model; only predefined example questions are supported |
| Both non-empty | Real Upstage model; requests may incur API charges |
| One missing or either empty | Startup error; no fallback |
| Authentication/network/model failure | Report the error; never switch to fake |

The quick-start loader accepts `KEY=VALUE`, blank lines, full-line `#` comments and values wrapped in matching single/double quotes. It does not expand variables, execute commands, parse inline comments or support multiline values. Invalid lines and duplicate model settings are rejected. Other well-formed variables are ignored.

### 3. Start with F5 or a terminal

**VS Code:** open the repository root, install the recommended Python and Python Debugger extensions, select **SQL agent - Quick start (auto)** and press **F5**.

**Terminal:** run the same launcher directly:

```powershell
.venv/Scripts/python.exe scripts/start.py
```

Both paths prepare `runs/local-debug/orders.sqlite` (synthetic data) and `runtime.json` if absent, then run the actual CLI. Existing DB/config files are preserved. The launcher selects the model for this run using a temporary config; it does not change the stored provider. Mode and DB path are printed to stderr without credential values. The default profile is `profiles/v1/profile.example.json` (2000 cents).

### 4. Send a question

Paste this single line into the running terminal, then press Enter:

```json
{"request_id":"demo-1","request":"이번 주 대형 주문은 몇 건인가요?","period":"2025-W03","timestamp":"2025-01-19T23:59:59Z"}
```

A successful response has `status: "ok"` and an `observation` containing SQL, answer text and reported values. A newly generated DB yields **2** large orders; an existing DB can yield a different count. Intermediate `stage` lines are stderr diagnostics; the final response is stdout JSONL. Use a new request ID for each subsequent request. Stop F5 with Shift+F5, or a terminal run with Ctrl+C.

## Explicit CLI configuration

For a custom DB/profile or explicit provider selection, edit a copy of `configs/runtime.example.json` and export credentials into the process environment when using Upstage:

```powershell
.venv/Scripts/python.exe -m driftlens_sql_agent --config configs/runtime.example.json --profile profiles/v1/profile.example.json --protocol-version v1
```

This command uses the provider in config and does **not** load `.env` or auto-select a model. DB paths are relative to the config file. See [configuration](configs/README.md) and [JSONL execution](docs/running.md).

## Development and limitations

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
```

Breakpoints do not suspend the model/request/SQL deadlines. See [debugging](docs/debugging.md), [contract](docs/contracts/v1/README.md) and [verification](docs/verification.md). The fixed live evaluation passed 36/36 supported and 24/24 unsupported cases; it is not an independent holdout or a guarantee for arbitrary questions. Explicit cent-conflict checks do not cover every natural-language expression.

Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [Apache-2.0](LICENSE).
