# DriftLens SQL Agent

[English](README.md) | [한국어](README.ko.md)

A single SQL agent for the DriftLens benchmark, currently at **phase 4: model and JSONL integration**. Config/profile validation, read-only SQLite, request isolation, budgets and observation-grounded answers are implemented. The fake model runs offline; Upstage HTTP and JSONL are implemented. Live model quality remains a separate evaluation.

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

The version `0.1.0.dev0` identifies this development package; it is not a release announcement. Run with `--config` and `--profile` to serve UTF-8 JSONL. See [running](docs/running.md), the [Python API](docs/runtime-phase-3.md), and the [requirement verification record](docs/verification.md). Help and version output are CLI discovery commands, not JSONL protocol output.

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

Phase 5 evaluates the live model before release review. The actual benchmark adapter remains separate work. This package does not perform drift detection or scoring.

## License

[Apache-2.0](LICENSE).

Live evaluation ran on 2026-10-22 with solar-pro4-260806: supported 36/36, unsupported refusals 21/24. The release gate failed because conflicting threshold requests were accepted. See [evaluation](evaluation/README.md) and [verification](docs/verification.md).
