# 004. Phase isolation — hardening, not microservices

- **Status**: Accepted
- **Date**: 2026-05-06
- **Phase**: 1 → 2 boundary

## Context

After Phase 1 stabilized (CV capture, sessions, fighter profiles, weight tracker), the user asked whether subsequent phase work could be split into microservices so changes to a new phase couldn't break work already done. The underlying concern — "Phase 2 changes shouldn't break Phase 1" — is legitimate. The proposed mechanism (microservices) carries large costs that don't pay back at this project's scale (single laptop, single user, IRB-mandated local-only deploy).

## Decision

Reject microservices. Adopt four lighter-weight mechanisms that deliver phase-isolation guarantees inside the existing hexagonal monolith:

1. **API versioning.** All Phase 1 routes are exposed under both unversioned paths (back-compat for the existing dashboard) and `/v1/...` (frozen contract). Phase 2+ routes whose response shape differs land under `/v2/...`. Old paths never change.

2. **Locked Phase 1 contract tests.** A pinned suite at `tests/contracts/test_v1_api_contract.py` captures every Phase 1 endpoint's status codes, response keys, and validation behavior. Failures here are versioning events — they're fixed by introducing `/v2`, not by relaxing assertions.

3. **Alembic-managed schema migrations.** `migrations/` holds versioned `revision` files. The baseline (`6554ed244684`) captures all Phase 1 tables (fighter, session, punch_event, hr_sample, weigh_in). Future schema changes are written as migrations; nobody wipes `data/alion.db` to add a column anymore. `make migrate` and `make migration MSG=…` are the entry points.

4. **Module-freeze rule for shipped phases.** Phase 1 packages — `packages/contracts`, `packages/store`, `packages/capture/cv`, `packages/analyze/punch_detector_heuristic`, `packages/api/routes/{fighters,sessions,health,cameras}`, `packages/api/services/capture_runner` — are feature-frozen. Bug fixes welcome; behavior or shape changes require an ADR plus a `/v2` route. New features land in *new* packages or sub-modules.

## Alternatives considered

- **True microservices** — independent processes per phase. Rejected: solves an organizational/scale problem we don't have. Costs (distributed-system complexity, observability, cross-service transactions, fusion-engine fragmentation) directly conflict with the dissertation's local-only / single-machine constraints. Documented separately in the explanation given to the user.
- **Branch-based phase isolation** (long-lived branches per phase) — rejected: Phase 4 fusion needs all streams in one process anyway, so a long-lived split doesn't model the eventual architecture.

## Consequences

- Positive: changes to a Phase 2+ module that accidentally touch a Phase 1 contract fail the test suite immediately. Schema evolution is data-preserving. The /v1 surface is now a stable target for any external tooling (validation-study scripts, future BoxRec integration).
- Negative: Phase 2 work has to think in versioned terms — a route that needs a new field on `SessionRead`, for instance, can't extend the v1 schema, it has to live under v2. Manageable; explicit.
- Follow-ups: when Phase 2 (HRV) ships its first new shape, write a `/v2/sessions` schema and a Phase-2-specific contract test file alongside `test_v1_api_contract.py`.
