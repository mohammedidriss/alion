# 002. SQLCipher encryption deferred to Phase 8

- **Status**: Accepted
- **Date**: 2026-05-04
- **Phase**: 0

## Context

IRB / SDAIA compliance requires athlete data encrypted at rest. SQLCipher is the chosen mechanism. The brief schedules it for Phase 8 (Hardening Before Field Deployment).

## Decision

Phases 0–7 use plain SQLite. **No real athlete data may be stored until Phase 8 lands.** Synthetic and self-test data only.

A pre-flight check (Phase 8 deliverable) will refuse to start a session if the DB is not encrypted.

## Alternatives considered

- **SQLCipher from day one** — extra dep, build complexity, slows Phase 0–7 iteration. The brief explicitly defers it.
- **Application-layer encryption** — leaks plaintext through query logs, indexes; SQLCipher is the standard.

## Consequences

- Positive: faster early iteration; clean swap path (driver-level change).
- Negative / risk: if a real athlete session lands in the DB before Phase 8, that's a compliance incident. Mitigation: README warning + the pre-flight gate in Phase 8.
- Follow-up: Phase 8 ADR will document the SQLCipher driver chosen and the key-management plan.
