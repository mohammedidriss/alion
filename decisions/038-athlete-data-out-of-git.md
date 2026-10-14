# 038. Athlete data and models trained on it stay out of git

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The repository says athlete data is never committed, yet three files from
training sessions were tracked (found by the Codex review):

- `data/labels/c71b080b-….json` — one session's punch times, hands and types;
- `data/ml/punches_dataset.csv` — 41 rows of pose coordinates around punches;
- `data/ml/punch_classifier_v1.pkl` — a small classifier trained on them.

None holds a name or other personal field, so they aren't a privacy leak, but
they break the rule and the repository is public.

## Decision

- The three files are untracked (`git rm --cached`): they stay on this computer —
  `capture_runner` still loads the classifier when it's there — and leave the
  repository from this commit on.
- `.gitignore` covers `data/labels/`, `data/ml/*.pkl` and `data/ml/*.csv`, so
  session labels, training rows and trained classifiers can't be added again.
- **History isn't rewritten.** Earlier commits still contain the files; removing
  them means rewriting the branch history and force-pushing, which every clone
  then has to follow — the owner's decision, not done here.

## Consequences

- A fresh clone has no `punch_classifier_v1.pkl`; the capture runner already
  carries on without it.
- Another checkout that pulls this commit has the three files deleted from its
  working tree (git removes files that leave the index); copy them first if
  that checkout needs them.
