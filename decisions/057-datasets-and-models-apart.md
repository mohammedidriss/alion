# 057. Datasets show data; the AI models page shows the models

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

The Research datasets page opened with two AI model cards — punch types from the
cameras and from the wrist sensors, which learn from every dataset (and since
ADR-047 from recorded sessions too) — above the one dataset, RQ2; the punch
counter's training sat inside RQ2's page. Model training was in two places, both
on a page meant for data, and nothing said what RQ2 is: the ground truth for
research question 2, recorded with protocol rq2-v1. A take left marked recording
(its capture gone) wasn't flagged anywhere. The owner asked (15 Oct 2026) for a
clearer organisation.

## Decision

- **Datasets** (the menu item, renamed from "Research datasets"): data only. Each
  dataset says what it's for — its description, or its protocol's purpose
  (`lib/protocols.ts`) — and counts participants, takes done, recording now and
  discarded, when it was last recorded, and warns about **stuck** takes: marked
  recording for over an hour with nothing recording into them (`/v2/datasets`
  `stuck_takes`, a take's `stuck`). "+ New dataset" replaces "+ Record dataset
  session", which created a dataset.
- **A dataset's page** follows the work, in steps: 1 · Participants & consent,
  2 · Record (each participant's progress through the protocol's blocks),
  3 · Check takes (stuck ones linked, discarded ones counted — files kept), and
  4 · Export (the de-identified copy, faces blurred).
- **AI models** (the menu item, renamed from "AI model"): every model in one
  place. Punch models — the camera punch counter (with a dataset picker), punch
  types from the cameras, punch types from the wrist sensors — each headed by
  what it does and what it learns from, then its training and score; and the
  coach's language model (ADR-021, ADR-049) on its own tab.

## Consequences

- `test_api_datasets.py`: the list's counts and a stuck take.
- No model changed; nothing moved on disk.
- On the live data RQ2 has 26 completed takes and none stuck; its three takes
  marked recording are unstarted drafts, which aren't listed or counted.
