# Camera (3D) + wrist punch types combined (research, 2026-10-14)

Branch `research/camera-wrist-fusion`. Nothing here changes the app or its models.

`scripts/studies/camera_wrist_fusion.py`: every typed punch of the 24 dataset
takes (1,472 punches, one participant, orthodox) gets the ADR-020 3D camera type
model's probabilities (averaged over the cameras that saw it) and the ADR-029
wrist type model's, then the two averaged ("mean") or multiplied ("product").
5-fold cross-validation grouped by take — both models trained on the other takes.
Results in `scripts/studies/camera_wrist_fusion_results.json`.

| | right | straight / hook / uppercut |
|---|---|---|
| wrist | 85.1 % | 90 / 83 / 76 % |
| camera, one view | 95.1 % | 98 / 93 / 90 % |
| **one camera + wrist** (product) | **96.6 %** | 100 / 95 / 91 % |
| camera, 3 views averaged | **97.5 %** | 100 / 95 / 96 % |
| 3 cameras + wrist (product) | 96.7 % | 100 / 94 / 93 % |
| 3 cameras + wrist (mean) | 95.9 % | 100 / 94 / 90 % |

**Findings.** With three cameras the camera model alone is best; the wrist adds
more errors than it fixes. With one camera the wrist helps (+1.5 points). Next, if
pursued: show the camera model's types after a session (three cameras), with the
wrist joining in only when one camera saw the punch — measured on one person, so
it needs other fighters' takes before it's trusted beyond them.
