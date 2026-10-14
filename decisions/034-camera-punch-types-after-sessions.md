# 034. The cameras name punch types after a session; the wrist fills in

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

Session punch types came from the wrist type model alone (ADR-029): 85 % on
held-out takes of the one person it learned from, about 50 % on other boxers.
The ADR-020 camera classifier (the arm's 3D motion relative to its shoulder)
scored better on the dataset takes (branch `research/camera-wrist-fusion`):

| who names the punch                   | held-out takes |
| ------------------------------------- | -------------- |
| one camera                            | 95.1 %         |
| one camera × the wrist                | 96.6 %         |
| two or more cameras, averaged         | 97.5 %         |
| the wrist alone                       | 85.1 %         |

The live, in-browser camera type rule scored 27.8 % and stays off (counts only)
until a browser-side model exists.

## Decision

- **A camera type model, trained from the takes** (`api.services.camera_type_model`):
  every completed take's typed labels, as each of its cameras saw them, no
  export step. Before the final fit it's scored on takes it never saw (5-fold,
  grouped by take), one camera at a time and with the take's cameras averaged.
  Saved as `data/ml/camera_types/v{n}.joblib` + `.json` (git-ignored).
  Researchers train and read it: `POST /v2/camera-types/train`,
  `GET /v2/camera-types`, the "Punch types from the cameras" card on Datasets.
- **The cross-check names each counted punch** (`cross_check._name_punches`), at
  the camera clock (camera time = wrist time + the camera's offset):
  - two or more cameras have a frame at it → the cameras' probabilities averaged
    (`motion_source: "cameras"`);
  - exactly one → that camera's probabilities × the wrist's, when the wrist felt
    it (`"camera+wrist"`), else the camera alone (`"camera"`);
  - none → the wrist model (`"wrist"`), as before.
  Jab / cross / lead / rear still come from the hand and the stance.
- **The camera model version is in the cross-check signature**, so training a
  new version re-names every session the next time it's opened.
- **The session breakdown says who named them**: "from the cameras", "from the
  wrist sensors" or both, the camera and wrist model versions and accuracies, and
  how many punches each source named.
- **Live stays counts only** (`LIVE_TYPES = false`).

## Consequences

- `tests/integration/test_camera_type_model.py`,
  `tests/integration/test_cross_check.py`.
- Trained on one participant, orthodox, one room: expect it to do worse on
  other fighters, camera placements and southpaws until their takes are in.
- Without a trained camera model nothing changes: the wrist names the punches.
