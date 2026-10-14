# Can BoxingVI's 2D pose teach the cameras punch types? (research, 2026-10-14)

Branch `research/boxingvi-camera-types`. Nothing here changes the app or its models.

**Data.** BoxingVI (Kumar et al., arXiv:2511.16524): the released 2D pose (COCO-17,
AlphaPose, one clip per punch) and labels for V1–V10 — 4,754 clips of 18 YouTube
athletes; no video downloaded; **no licence stated** (evaluation only). This
project: 1,472 typed punches in 24 dataset takes (one participant, orthodox),
each seen by 3 cameras (4,414 views). Labels: protocol blocks, timed by the wrist
sensors and reviewed.

**Method.** `analyze/pose2d_types.py` turns a punch's 2D keypoints into one row
(normalised to the shoulders, the arm that moved most, resampled to 16 frames,
mirror-augmented); gradient boosting over straight / hook / uppercut.
`scripts/studies/boxingvi_camera_types.py` scores, on this project's punches:

| | right | straight / hook / uppercut |
|---|---|---|
| BoxingVI on BoxingVI (videos held out) — feature check | 69.8 % | 79 / 59 / 58 % |
| live rule (`punch_type_heuristic`, the camera box) | **27.8 %** | 33 / 36 / 1 % |
| BoxingVI 2D model (other people only) | 51.0 % | 90 / 9 / 10 % |
| this project's 2D (takes held out) | 94.9 % | 98 / 92 / 91 % |
| BoxingVI + this project's 2D (takes held out) | 94.6 % | 98 / 92 / 89 % |
| ADR-020 3D camera model (takes held out) | **95.5 %** | 99 / 93 / 89 % |

**Findings.** BoxingVI's 2D doesn't transfer to these cameras (YouTube angles,
2D) and adds nothing when mixed in — not integrated. The live rule is below
chance on these punches. The 3D camera model trained on this project's takes is
the best namer — on the one participant it saw.

**2D + 3D.** Shared 2D features (tested here: no gain); late fusion of models'
probabilities (see `research/camera-wrist-fusion`); lifting BoxingVI to 3D with a
pose-lifting network, or triangulating this project's 3 synced phones into true
3D — both larger projects.
