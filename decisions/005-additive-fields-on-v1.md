# 005. Additive optional fields on v1 schemas are not contract changes

- **Status**: Accepted
- **Date**: 2026-05-06
- **Phase**: 1 lock + Phase 2 staging

## Context

ADR 004 froze the `/v1` API surface. The original contract tests in `tests/contracts/test_v1_api_contract.py` used strict equality (`==`) to compare response key sets, which would treat *any* added field as a contract violation — including additions that don't break existing consumers.

In practice, a v1 consumer that reads `response["name"]` doesn't care whether the response also gained a new optional `nickname` field. Strict equality is too aggressive a definition of "breaking change" for typical REST APIs.

## Decision

Refine ADR 004's contract rule:

**Breaking changes (require `/v2`):**
- Removing a field from a response
- Changing the type of an existing field
- Changing the meaning/semantics of a field
- Changing or removing an enum value that callers may already be matching against
- Changing a status code for an existing path/condition
- Changing required-ness of a request field

**Non-breaking (allowed on `/v1`, no version bump):**
- Adding a new optional field to a response (consumers ignore unknown keys)
- Adding a new optional request field with a sensible default
- Adding a new endpoint
- Adding a new enum value if existing code falls through gracefully on unknown values

## Implementation

`tests/contracts/test_v1_api_contract.py` is updated:
- Required-key checks switch from `set(body.keys()) == {…}` to `{…} <= set(body.keys())` — the listed keys must be present, additions are allowed.
- Enum-value checks remain strict equality where the values are public contract (e.g., `stances` exact set).

If a Phase 2 PR ever wants to remove a v1 key or change a type, the contract test fails — and the right fix is `/v2`, never relaxing the test.

## Consequences

- Positive: Phase 2 work that legitimately enriches existing models (e.g., adding `punch_type` to `PunchEvent`) doesn't require a full `/v2` plumbing.
- Negative: contract tests no longer pin the *exact* shape, only the required floor. Mitigated by the explicit list of breaking-change kinds above and a CI check.
- Follow-ups: any future contract test should follow this pattern (list required keys, use subset assertion) so the rule is uniform.
