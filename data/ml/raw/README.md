# Public datasets — pretraining the LSTM second-pass

The trainer expects two on-disk video folders that this repo does **not**
ship (each is several GB and has its own licence). Lay them out like
this and the prep script picks them up automatically.

```
data/ml/raw/
├── ucf101/
│   └── videos/
│       ├── BoxingPunchingBag/
│       │   ├── v_BoxingPunchingBag_g01_c01.avi
│       │   └── …
│       ├── BoxingSpeedBag/…
│       └── Punch/…
└── hmdb51/
    └── videos/
        ├── punch/…
        └── boxing/…
```

## Where to get them

- **UCF101**: <https://www.crcv.ucf.edu/data/UCF101.php> — download the
  full archive (~6.5 GB). After extracting, copy or symlink the
  `BoxingPunchingBag/`, `BoxingSpeedBag/`, and `Punch/` class folders
  under `ucf101/videos/`.
- **HMDB-51**: <https://serre-lab.clps.brown.edu/resource/hmdb-a-large-human-motion-database/>
  — download the videos archive (~2 GB). Move the `punch/` and
  `boxing/` (if present) class folders under `hmdb51/videos/`.

Both datasets need their own academic-use agreements; review them
before downloading.

## Optional: negatives

To balance the binary classifier, also place non-punch clips under
`data/ml/raw/negatives/<class_name>/`. Any subfolder name other than
the punch class names is treated as a negative example. UCF101's
`PullUps`, `PushUps`, `JumpingJack`, `BodyWeightSquats` are good
domain-similar negatives.

## Run the prep script

```bash
uv run python -m scripts.ml.prep_public_dataset \
  --ucf101 data/ml/raw/ucf101/videos \
  --hmdb51 data/ml/raw/hmdb51/videos \
  --negatives data/ml/raw/negatives \
  --out data/ml/datasets/punch_windows.parquet
```

Then train:

```bash
uv pip install torch
uv run python -m scripts.ml.train_punch_lstm \
  --in data/ml/datasets/punch_windows.parquet \
  --out data/ml/punch_lstm_v1.pkl \
  --epochs 30
```

The trained model lands at `data/ml/punch_lstm_v1.pkl`. The runtime
loader (`analyze.lstm_second_pass.LSTMSecondPass.try_load()`) auto-
detects it and `default_second_pass()` will use it instead of the
stricter heuristic.
