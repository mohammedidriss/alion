# Alion

Multi-modal AI coaching platform for combat sports. Validation artifact for a DBA dissertation at Golden Gate University. Boxing is the validation domain.

**Not a medical device. Not a diagnostic tool. Advisory only.**

> Agents and contributors: read [`CLAUDE.md`](CLAUDE.md) before making structural changes.

## Quick start (native dev)

Prerequisites: macOS, `uv`, Node 20, `pnpm` (`brew install pnpm`).

```bash
# Python deps (includes MediaPipe + OpenCV)
uv sync --extra dev --extra capture

# Run the API
uv run uvicorn api.main:app --reload   # http://localhost:8000

# In another terminal: dashboard
cd apps/dashboard
pnpm install
pnpm dev                                # http://localhost:3000

# Live webcam capture (with cv2 preview window)
uv run python scripts/record_live.py --fighter <FIGHTER_UUID> --show

# Or process an existing MP4
uv run python scripts/process_video.py path/to/clip.mp4 --fighter <FIGHTER_UUID>
```

Docker is removed for now. We'll bring it back at the end of the project once all phases are complete.

## Architecture

Three sensor streams (CV / IMU / HRV) → Fusion Engine → LLM Coaching Layer. Hexagonal (ports & adapters) — see [`CLAUDE.md`](CLAUDE.md#architecture-hexagonal--ports--adapters) for the role of each `packages/*` directory.

The architecture contract (no cross-imports between feature modules) is enforced by `import-linter` in pre-commit and CI.

## Verify

```bash
make verify              # ruff + format + mypy --strict + import-linter + pytest
make fresh-clone-check   # simulate a clean checkout end-to-end
```

## Environment variables

All settings use the `ALION_` prefix. See `.env.example`. Notable:

- `ALION_DB_PATH` — SQLite file path (default `./data/alion.db`).
- `ALION_DATABASE_URL` — overrides `ALION_DB_PATH`. Useful later when we point at Postgres.
- `ALION_LOG_LEVEL` — INFO / DEBUG / WARNING.
- `ALION_LM_STUDIO_URL` — for the LLM coaching layer (Phase 5+).

## Data & privacy

- **Local-only.** No cloud transfer of athlete data (IRB / SDAIA constraint).
- `data/raw/` and `data/processed/` are gitignored.
- SQLCipher encryption lands in Phase 8.

## Decisions

Architecture decisions are recorded in [`decisions/`](decisions/). Every non-obvious choice gets an ADR.

## Status

**Phase 1 Week 1** — CV capture: live webcam + MP4 upload + heuristic punch detection. In progress.
