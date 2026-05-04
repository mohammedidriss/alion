# 001. Module boundaries — independent but integrated

- **Status**: Accepted
- **Date**: 2026-05-04
- **Phase**: 0

## Context

The brief mandates a modular architecture where changing one module must not break others. With ten Python packages plus a frontend, the easy failure mode is silent cross-imports that couple feature modules over time.

## Decision

Two-tier dependency DAG, enforced mechanically:

- **Tier 1 (foundations)**: `contracts`, `common`. Depended on by everything; depend on nothing in this repo.
- **Tier 2 (feature modules)**: `store`, `capture`, `analyze`, `fusion`, `grounding`, `coach`, `studies`. May depend on Tier 1 only. **Must not import from each other.**
- **Tier 3 (composition root)**: `api`. The only place feature modules are wired together.

`import-linter` enforces this in pre-commit and CI. Violations fail the build.

Inter-module communication is via `contracts/` types — never via direct imports.

## Alternatives considered

- **Honour-system "please don't cross-import"** — fails within weeks under deadline pressure.
- **uv workspaces with one package per directory** — stronger isolation, but ~10× more pyproject.toml files to maintain. Overkill for a solo dissertation project.
- **Microservices** — absurd for a single-laptop validation study.

## Consequences

- Positive: changing the LSTM in `analyze` cannot ripple into `coach`. Tests run module-by-module.
- Negative: every cross-module data flow goes through `contracts/`. Schema changes are the one event that ripples — handled with `schema_version` + ADR.
- Follow-up: when `fusion/engine` lands in Phase 4, it must produce `SessionSummary` directly; downstream modules must not reach into fusion internals.
