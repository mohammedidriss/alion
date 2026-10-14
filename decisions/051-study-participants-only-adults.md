# 051. Only adult study participants use Alion, and all data trains the models

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The owner decided (14 Oct 2026) that the people who agree to take part in the
study are the only people who sign in, that nobody under 18 takes part, and
that therefore all data — sessions and datasets alike — is used to train the AI
models. ADR-047 already trains the models on recorded sessions without a
separate choice; the terms said recordings develop the models, but not who may
take part.

## Decision

- **Terms draft-4**: a new section 2, "Who can take part" — accepting the terms
  is the agreement to take part, nobody signs in without it (as before,
  ADR-016), and participants are 18 or older. Section 6, "How your data is
  used", says all data on the platform — sessions, labels and notes, health
  notes, research datasets — is used to develop, train and evaluate the models,
  with no separate choice while using Alion; to stop, withdraw (section 9, now
  covering the study as well as a dataset).
- The agreement on the sign-up form and on the terms screen reads "I am 18 or
  older, and I agree to take part in the study and to the terms". Accepting the
  current version records it; there is no separate age field.
- No guardian or minor features are built (ADR-050).

## Consequences

- Everyone accepts the terms again (draft-4).
- An account a gym or an administrator creates is asked to accept, with the
  age confirmation, at its first sign-in.
- The terms file is still marked as a draft to be replaced by the wording the
  study's ethics board approves.
