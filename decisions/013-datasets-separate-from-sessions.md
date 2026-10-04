# 013. Datasets — a recording system separate from training sessions

- **Status**: Accepted
- **Date**: 2026-10-04
- **Phase**: 6 (datasets / RQ2)

## Context

RQ2 needs a labelled punch dataset: video from several angles, both wrist IMUs and
heart rate, recorded while a fighter works through a scripted protocol ("30 jabs,
30 crosses, …"). The first plan recorded those drills as ordinary training
sessions with a protocol card on the session page. That mixes two different things:

- **Stats.** Scripted drills would flow into the fighter's punch counts, trends,
  readiness and comparisons — numbers meant to describe real training.
- **Governance.** Recording other fighters needs a signed IRB consent per
  participant (ADR-002 keeps real athlete data out until then; the researcher may
  record himself). A dataset must be exportable, and a participant's data
  deletable, as a unit — awkward when it's scattered through session tables.
- **Workflow.** A take needs a protocol prompter, label progress and per-class
  counts; it doesn't need the round timer, scoreboard or coaching panels.

The coach asked for a separate tab for creating datasets and recording takes, and
chose a **fully separate system** over tagging sessions.

## Decision

Datasets get their own model, storage, API and UI. A **take** is a dataset
recording; it is never a `Session`, and no take data lands in session tables.

**Storage — files, one folder per take** (gitignored, `data/datasets/`):

```
data/datasets/{dataset_id}/takes/{take_id}/
  take.json      fighter, stance, devices (+ each clip's start_offset_ms), t0 (wall ms),
                 duration, status, notes — written only by the take store
  video/{device_id}.webm        one clip per camera (laptop, phones)
  pose/{device_id}.parquet      each camera's pose stream (the pose LSTM trains on it)
  imu.csv        t_ms,hand,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps
  hr.csv         t_ms,rr_ms,hr_bpm
  protocol.json  protocol blocks + labelling provenance — written only by the protocol side
  labels.json    [{t_ms, hand, punch_type}] — the format studies.evaluation.load_labels reads
```

Each file has one writer, so the two halves of the system never race on a file.

Files, not tables, because a dataset is consumed as files (training, export,
sharing with a committee), and deleting a participant is deleting their take
folders. **DB tables only index** the files and enforce consent:

- `dataset` — name, description, protocol key, created_at.
- `dataset_participant` — dataset × fighter, consent `self | irb_signed | pending |
  withdrawn`, consent date, IRB reference. Takes can only be recorded for
  `self` or `irb_signed`.
- `dataset_take` — dataset, fighter, status `recording | completed | discarded`,
  started/ended, duration, notes.

**Timeline** is the session one (ADR-006/010): `t_ms` counts from the cameras'
synchronized start, so video, IMU and protocol blocks line up exactly as they do
for sessions. **Takes have no Pause** — the protocol rests between blocks, and a
node applies a pause up to one heartbeat (400 ms) after the server, which would
blur the labels — so a take's timeline is simply `wall_ms − t0`.
`capture_coord.timeline_now_ms(take_id)` gives "now" on it (for block markers);
`dataset_store.take_dir(take_id)` resolves a take's folder.

**Capture engines are shared, not copied.** The camera coordinator (ADR-010), the
wrist-IMU recorder and the Polar stream already solve the hard parts (sync start,
pause, upload, BLE crash isolation, sample timing). They gain a *capture target*:
a session target writes where it always has; a take target writes into the take
folder (clips → `video/`, IMU rows → `imu.csv`, HR rows → `hr.csv`). The
coordinator's device/start/pause/stop/upload routes are mounted under both
`/sessions/{id}/multicam/*` (unchanged) and `/takes/{id}/multicam/*`; only the
join and complete steps differ per kind. Phones join a take at
`/takes/{id}/camera`.

**UI** — a **Datasets** entry in the sidebar:

- `/datasets` — datasets, create one.
- `/datasets/{id}` — participants with consent status, takes with their data
  (clips, IMU samples, labels), "Record take".
- `/datasets/{id}/takes/{take_id}` — the recording screen: live reader, cameras
  panel, join QR, the protocol prompter; after Stop, the take's clips and data.

Training views never see takes, so no filtering is needed anywhere else.

**Ownership** (two sessions build this in parallel):

- Capture + platform: the tables and migration, the take folder store, the capture
  target in the coordinator / IMU / Polar engines, the API, the Datasets tab, the
  dataset page and the recording screen.
- Protocol + labels: protocol definitions and block start/end keyed on the take,
  the `ProtocolCard` (takes a `takeId`, mounted in the recording screen), the IMU
  auto-labeller reading `imu.csv` and writing `labels.json`, the dataset export
  (manifest + splits), and `docs/studies/RQ2_DATASET_PROTOCOL.md`.

## Alternatives considered

- **Tag sessions with a purpose** (`Session.purpose = dataset`) and filter them
  out of training views. Least code, and recording would be untouched — rejected
  by the coach in favour of full separation: every training view would need the
  filter forever, and dataset governance would still be spread across session
  tables.
- **Separate system with its own copy of the recorders.** Rejected: the camera
  coordinator and BLE recorders are the most fragile code in the platform;
  two copies would drift. A capture target gives the same separation with one
  recorder.
- **Take data in DB tables** (`take_imu_sample`, …). Rejected: the dataset is
  consumed as files, and per-participant deletion and export are simpler on
  folders. The DB keeps the index and the consent rules.

## Consequences

- Training stats can't be polluted by drills, and a dataset can be exported,
  shared or deleted per participant without touching sessions.
- Consent is enforced at take creation, which is where IRB status matters.
- Take data is plain files: there is no DB-level integrity between `imu.csv` and
  `dataset_take`; the store owns the folder layout and is the only writer.
- Real athlete data on disk is unencrypted until Phase 8 (ADR-002) — the same
  status as session data today; `data/datasets/` is gitignored.
- Follow-ups: pose streams for takes (recomputable from the clips meanwhile),
  encryption at rest (Phase 8), consent-withdrawal deletion flow.
