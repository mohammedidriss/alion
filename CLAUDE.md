# CLAUDE.md — agent guide for the Alion repository

This file is the primary brief for any AI agent (or new human contributor) working in this repo. Read it before making structural changes.

## What this is

Alion is the validation artifact for a DBA dissertation at Golden Gate University: a multi-modal AI coaching platform for combat sports (boxing as the validation domain). Three sensor streams (CV, IMU, HRV) → fusion engine → LLM coaching layer. **Not a medical device. Not diagnostic. Advisory only.** All athlete data is local-only (IRB / SDAIA compliance).

The full vision lives in `Combat_Intel_Build_Brief.md` (referenced from outside the repo).

## Architecture (Hexagonal — Ports & Adapters)

The folder names don't say "domain" or "infrastructure", but the separation is real and enforced mechanically by `import-linter`:

| Hexagonal role | Folder | Notes |
|---|---|---|
| **Domain (core types)** | `packages/contracts/` | Pure pydantic. Zero dependencies on infra. Everyone imports from here. |
| **Domain ports (Protocols)** | `packages/contracts/`, `packages/capture/cv/sources.py` (`FrameSource` Protocol) | Idiomatic Python — `Protocol`, not ABC. |
| **Cross-cutting primitives** | `packages/common/` | Settings, logging, time utils. Depended on by everything; depends on nothing. |
| **Infrastructure adapters** | `packages/store/` (SQLite/Postgres), `packages/capture/` (CV/IMU/HRV drivers), `packages/coach/` (LM Studio), `packages/grounding/` (hallucination harness), `packages/analyze/` (LSTM, heuristics) | Each is independent — sibling adapters cannot import each other. |
| **Composition root (use cases + DI)** | `packages/api/` | The only module allowed to wire adapters together. FastAPI `Depends()` is the DI mechanism. |
| **Web / UI** | `apps/dashboard/` (Next.js) | Talks to `api/` over HTTP. |

**The DAG is enforced.** `uv run lint-imports` fails the build if a feature module cross-imports another. The contract is in `pyproject.toml` under `[tool.importlinter]`.

## Tech stack (decisions made; do not relitigate)

- Python 3.11, `uv` for dependency management
- FastAPI + SQLModel + Pydantic 2
- SQLite by default; Postgres via `docker compose --profile postgres`
- Next.js 14 (app router) + Tailwind, `pnpm`
- MediaPipe Tasks API + OpenCV (lazy-imported; live in `[capture]` extras)
- LM Studio locally for the LLM (Phase 5+); Anthropic API only as a fallback for prompt-engineering experiments
- Quality gates: ruff (lint + format), mypy --strict, import-linter, pytest, pre-commit

## Build commands

```bash
# Native (host machine)
uv sync --extra dev                    # core install
uv sync --extra dev --extra capture    # adds MediaPipe + OpenCV
uv run uvicorn api.main:app --reload   # API on :8000
cd apps/dashboard && pnpm install && pnpm dev   # dashboard on :3000

# Docker (single command)
docker compose up --build              # SQLite default
docker compose --profile postgres up --build   # swap in Postgres
```

## Test commands

```bash
make verify                      # lint + format + types + arch + tests
uv run pytest -v                 # tests only
uv run pytest tests/unit/...     # one file
uv run mypy packages             # types only
uv run ruff check . && uv run ruff format --check .
uv run lint-imports              # architecture
make fresh-clone-check           # simulate a fresh clone end-to-end
```

## Project structure

```
alion/
├── packages/                # All Python source
│   ├── contracts/           # Domain — pydantic types (the law)
│   ├── common/              # Settings, logging, time
│   ├── store/               # DB adapter (SQLite + Postgres via DI)
│   ├── capture/             # cv/, hrv/, imu/ — independent adapters
│   ├── analyze/             # Heuristics, LSTM (Phase 3)
│   ├── fusion/              # session_summary.json builder (Phase 4)
│   ├── grounding/           # Hallucination harness (Phase 5)
│   ├── coach/               # LM Studio client + prompts (Phase 5)
│   ├── studies/             # Validation-study mode (Phase 7)
│   └── api/                 # Composition root — FastAPI + services
├── apps/dashboard/          # Next.js coach UI
├── tests/                   # unit/, integration/, fixtures/
├── scripts/                 # CLI: record_live.py, process_video.py
├── decisions/               # ADRs — every non-obvious choice
├── data/                    # gitignored — raw + processed athlete data
├── models/                  # gitignored — trained weights, MediaPipe assets
├── Dockerfile.api
├── Dockerfile.dashboard
├── docker-compose.yml
├── pyproject.toml
└── CLAUDE.md                # this file
```

## Style guide

- **Type everything.** Python: full hints + pydantic for data. TypeScript: no `any`. mypy strict and tsc must pass.
- **Default to no comments.** Code should explain itself; comments only for non-obvious *why* (constraints, invariants, workarounds).
- **Schema is law.** Changes to `packages/contracts/` ripple to every dependent module by design. Bump `SCHEMA_VERSION` and update tests + fixtures + prompts in the same commit.
- **No cross-imports between feature modules.** If you find yourself wanting to `from analyze import …` inside `coach/`, the data needs to flow through `contracts/` instead, with the wiring in `api/`.
- **Lazy-import heavy deps.** MediaPipe, OpenCV, etc. are imported inside functions/context managers so that machines without `[capture]` extras can still import the modules.
- **Lint via `uv run`.** Both pre-commit hooks and CI invoke ruff/mypy/pytest through `uv run`, so versions come from `pyproject.toml` + `uv.lock` — no version drift between local and CI.
- **Small commits, conventional messages.** Every commit must build, test, and lint clean.
- **ADR every non-obvious decision.** Add a markdown file under `decisions/`.

## Do this / don't do this

- ✅ Add a new infrastructure adapter? Create `packages/<name>/`, depend only on `contracts` + `common`, register in `pyproject.toml` `[tool.hatch]` and `[tool.importlinter]`.
- ✅ Need to wire two feature modules? Do it in `api/services/`. That's the composition root.
- ❌ Don't put working code in any `.runtime/`, sandbox, or scratch directory. Everything tracked by git. The `make fresh-clone-check` target proves a clean checkout works.
- ❌ Don't commit athlete data, secrets, model binaries, or `.env` files. `data/`, `models/**/*.task`, `*.db`, `.env` are all gitignored.
- ❌ Don't introduce backwards-compatibility shims, dead `# removed` comments, or feature flags for hypothetical future requirements. Change the code.
- ❌ Don't bypass the architecture contract by `# noqa` or `# type: ignore` to silence import-linter. If a real cross-cutting concern emerges, it belongs in `common/` or `contracts/`.

## Caveats and known limits

- **Live webcam capture does NOT work inside Docker on macOS** (no `/dev/video0` passthrough). Use `scripts/record_live.py` on the host for that. MP4 upload + processing works in-container.
- **LM Studio runs on the host.** Apple Metal acceleration is unavailable inside Docker; the API container talks to `host.docker.internal:1234`.
- **MediaPipe model is downloaded on first use** into `models/mediapipe/pose_landmarker_lite.task` (~5.5 MB). It's gitignored.
- **Encryption-at-rest is deferred to Phase 8.** Until SQLCipher lands, only synthetic / self-test data should hit the DB. See `decisions/002-encryption-deferred.md`.

## When asked to add a new feature

Default to: (1) state which phase from the brief this belongs in; (2) propose where it lives in the hexagonal map above; (3) confirm before scaffolding more than one file. Don't conflate phases — the brief's ordering (capture → analyze → fusion → coach) is intentional.
