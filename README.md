# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

A single SQL agent for the DriftLens benchmark, currently at **phase 3: bounded runtime core**. Config/profile validation, read-only SQLite, request isolation, budgets and observation-grounded answers are implemented. The deterministic fake model runs offline; live Upstage and JSONL transport are pending phase 4.

## Install and inspect

Python 3.11 or later. From this repository in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/driftlens-sql-agent.exe --help
.venv/Scripts/python.exe -m driftlens_sql_agent --version
.venv/Scripts/python.exe -m unittest discover -s tests/unit -p "test_*.py" -v
```

On other platforms use the corresponding environment executables under `.venv/bin/`. No benchmark checkout, API key or runtime dependency is required for these package checks. Installing the build backend may require package-index access.

The version `0.1.0.dev0` identifies this development package; it is not a release announcement. Runtime invocation with `--config` and `--profile` currently exits with code 2, no stdout, and `transport_not_implemented` on stderr. Use the [Python API](docs/runtime-phase-3.md) for offline execution. Help and version output are CLI discovery commands, not JSONL protocol output.

## Layout and status

| Path | Purpose |
| --- | --- |
| `src/driftlens_sql_agent/` | Settings, SQL tool, bounded runtime, model boundary and CLI discovery |
| `pyproject.toml` | Build metadata, Python requirement and console entry point |
| `tests/unit/` | CLI, settings, temporary SQLite and isolated model tests |
| `configs/`, `profiles/` | v1 examples loaded through the Python API |
| `docs/contracts/v1/` | Contract and future validation requirements |

See the [cleanup record](docs/migration-phase-2.md), [architecture status](docs/README.md), [v1 contract](docs/contracts/v1/README.md), and [validation plan](docs/contracts/v1/validation.md). Documents are primarily Korean. Collaborators follow [CONTRIBUTING.md](CONTRIBUTING.md); AI instructions are in [AGENTS.md](AGENTS.md).

## Next phases

Phase 4 adds the model/JSONL connection and CI. Phase 5 evaluates the live model before release review. The actual benchmark adapter remains separate work. This package does not perform drift detection or scoring.

## License

[Apache-2.0](LICENSE).
