# Combat Intel

Multi-modal AI coaching platform for combat sports. Validation artifact for a DBA dissertation at Golden Gate University. Boxing is the validation domain.

**Not a medical device. Not a diagnostic tool. Advisory only.**

## Architecture

Three sensor streams (CV / IMU / HRV) → Fusion Engine → LLM Coaching Layer. See [`Combat_Intel_Build_Brief.md`](../../My%20Documents/Personal/Doctorate%20Program-Upgrad/9-Immersion%20course/Immersion1_Topic_Presentation_Boxing/Combat_Intel_Build_Brief.md) for the locked architecture.

## Module layout

All source code lives under `packages/` (Python) and `apps/` (frontend). Modules communicate only through the `contracts/` schema; cross-module imports are forbidden by `import-linter` (enforced in CI).

| Module | Role |
|---|---|
| `contracts` | Pydantic schema — the law |
| `common` | Settings, logging, time utils |
| `store` | SQLModel + SQLite |
| `capture` | CV / IMU / HRV / sync ingestion |
| `analyze` | Pose, punch classifier, HRV metrics |
| `fusion` | session_summary.json builder |
| `grounding` | Hallucination harness |
| `coach` | LLM client + prompts |
| `studies` | Validation-study mode |
| `api` | FastAPI — composition root |
| `apps/dashboard` | Next.js coach UI |

## Setup (fresh clone)

```bash
# Python side
uv sync --extra dev

# Run tests
uv run pytest

# Lint + type check + architecture
uv run ruff check .
uv run ruff format --check .
uv run mypy packages
uv run lint-imports

# API
uv run uvicorn api.main:app --reload

# Dashboard (requires pnpm: brew install pnpm)
cd apps/dashboard
pnpm install
pnpm dev
```

Or run everything:

```bash
make verify
```

## Data & privacy

- **Local-only.** No cloud transfer of athlete data (IRB / SDAIA constraint).
- `data/raw/` and `data/processed/` are gitignored.
- SQLCipher encryption lands in Phase 8.

## Decisions

Architecture decisions are recorded in [`decisions/`](decisions/). Every non-obvious choice gets an ADR.

## Status

**Phase 0** — skeleton complete. See the brief's §5 for the full phase plan.
