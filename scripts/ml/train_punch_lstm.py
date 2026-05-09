"""Train the LSTM second-pass punch classifier.

Reads `data/ml/datasets/punch_windows.parquet` (produced by
`prep_public_dataset.py`) and trains a small LSTM to classify each
30-frame window of MediaPipe Pose keypoints as `punch` or `other`.

Output: `data/ml/punch_lstm_v1.pkl` — a pickled dict containing model
state_dict, normalisation stats, window length, and feature dim. This
file is what `analyze.lstm_second_pass.LSTMSecondPass.try_load()`
picks up at runtime.

Run:
    uv run python -m scripts.ml.train_punch_lstm \
        --in data/ml/datasets/punch_windows.parquet \
        --out data/ml/punch_lstm_v1.pkl \
        --epochs 30 --batch-size 32

Requires PyTorch. Install with:
    uv pip install torch
"""

from __future__ import annotations

import argparse
import pickle
import random
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

LABELS = ["other", "punch"]


def _load_windows(parquet: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Returns (X[N,T,F], y[N], label_index)."""
    table = pq.read_table(parquet)
    cols = table.column_names
    feat_cols = sorted(
        (c for c in cols if c.startswith("f") and c.endswith("_x")),
        key=lambda c: int(c[1:].split("_", 1)[0]),
    )
    if not feat_cols:
        raise SystemExit("no feature columns found in parquet")
    label_arr = table.column("label").to_pylist()
    feature_matrix = np.column_stack(
        [table.column(c).to_numpy(zero_copy_only=False) for c in feat_cols]
    ).astype(np.float32)
    n_windows = feature_matrix.shape[0]
    feat_dim_total = feature_matrix.shape[1]
    # Infer T (frames) and F (features per frame). Heuristic: the
    # prep script writes 264 features per frame; let the user override
    # via the parquet metadata if needed.
    n_features_per_frame = 264
    if feat_dim_total % n_features_per_frame != 0:
        raise SystemExit(
            f"feature column count {feat_dim_total} not divisible by 264 — "
            "did the prep script change the schema?"
        )
    T = feat_dim_total // n_features_per_frame
    X = feature_matrix.reshape(n_windows, T, n_features_per_frame)
    y = np.array([LABELS.index(label) for label in label_arr], dtype=np.int64)
    return X, y, LABELS


def _stratified_split(
    X: np.ndarray, y: np.ndarray, val_frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    train_idx: list[int] = []
    val_idx: list[int] = []
    for c in np.unique(y):
        idxs = np.where(y == c)[0]
        rng.shuffle(idxs)
        n_val = max(1, int(len(idxs) * val_frac))
        val_idx.extend(idxs[:n_val].tolist())
        train_idx.extend(idxs[n_val:].tolist())
    rng.shuffle(np.array(train_idx))
    return X[train_idx], y[train_idx], X[val_idx], y[val_idx]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=Path("data/ml/datasets/punch_windows.parquet"),
    )
    ap.add_argument("--out", type=Path, default=Path("data/ml/punch_lstm_v1.pkl"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not args.inp.exists():
        raise SystemExit(f"input parquet not found: {args.inp}")

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as e:
        raise SystemExit("PyTorch not installed. Run: uv pip install torch") from e

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    X, y, labels = _load_windows(args.inp)
    print(f"loaded {len(X)} windows · shape {X.shape} · labels {Counter(y.tolist())}")

    Xtr, ytr, Xva, yva = _stratified_split(X, y, args.val_frac, args.seed)
    print(f"train={len(Xtr)} · val={len(Xva)}")

    # Normalise features by per-feature mean/std on the train split.
    mean = Xtr.reshape(-1, X.shape[-1]).mean(0).astype(np.float32)
    std = Xtr.reshape(-1, X.shape[-1]).std(0).astype(np.float32) + 1e-6
    Xtr_n = (Xtr - mean) / std
    Xva_n = (Xva - mean) / std

    train_ds = TensorDataset(torch.from_numpy(Xtr_n).float(), torch.from_numpy(ytr).long())
    val_ds = TensorDataset(torch.from_numpy(Xva_n).float(), torch.from_numpy(yva).long())
    tr = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    va = DataLoader(val_ds, batch_size=args.batch_size)

    class PunchLSTM(nn.Module):
        def __init__(self, feat_dim: int, hidden: int, n_classes: int) -> None:
            super().__init__()
            self.lstm = nn.LSTM(feat_dim, hidden, num_layers=1, batch_first=True)
            self.head = nn.Linear(hidden, n_classes)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out, _ = self.lstm(x)
            # Mean-pool over time, then classify.
            return self.head(out.mean(dim=1))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = PunchLSTM(X.shape[-1], args.hidden, len(labels)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    # Class-weighted loss — datasets with continuous-stream labelling
    # (Olympic Boxing) are heavily imbalanced (~6% punch). Without
    # weighting the model collapses to "always predict other".
    counts = np.bincount(ytr, minlength=len(labels)).astype(np.float32)
    weights = (len(ytr) / (len(labels) * np.maximum(counts, 1.0))).astype(np.float32)
    print(f"class counts (train): {dict(zip(labels, counts.tolist(), strict=True))}")
    print(f"class weights:        {dict(zip(labels, weights.tolist(), strict=True))}")
    loss_fn = nn.CrossEntropyLoss(weight=torch.from_numpy(weights).to(device))

    def _per_class_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, float]:
        out: dict[str, float] = {}
        for i, name in enumerate(labels):
            tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == i and p == i)
            fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != i and p == i)
            fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == i and p != i)
            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            f1 = 2 * prec * rec / max(prec + rec, 1e-9)
            out[f"{name}_p"] = prec
            out[f"{name}_r"] = rec
            out[f"{name}_f1"] = f1
        return out

    best_val = 0.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for xb, yb in tr:
            xb = xb.to(device)
            yb = yb.to(device)
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yb)
            loss.backward()
            opt.step()
            running += loss.item() * len(xb)
        running /= len(tr.dataset)

        model.eval()
        correct = 0
        total = 0
        all_y: list[int] = []
        all_p: list[int] = []
        with torch.no_grad():
            for xb, yb in va:
                xb = xb.to(device)
                yb = yb.to(device)
                pred = model(xb).argmax(1)
                correct += (pred == yb).sum().item()
                total += len(yb)
                all_y.extend(yb.cpu().tolist())
                all_p.extend(pred.cpu().tolist())
        val_acc = correct / max(total, 1)
        cls = _per_class_metrics(all_y, all_p)
        # Use F1 of the minority "punch" class as the model-selection
        # metric — accuracy is meaningless on a 6% positive split.
        punch_f1 = cls.get("punch_f1", 0.0)
        print(
            f"ep {epoch:>3d}  loss={running:.4f}  val_acc={val_acc:.3f}  "
            f"punch[p={cls.get('punch_p', 0):.3f} r={cls.get('punch_r', 0):.3f} "
            f"f1={punch_f1:.3f}]"
        )

        if punch_f1 > best_val:
            best_val = punch_f1
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("wb") as f:
                pickle.dump(
                    {
                        "state_dict": {k: v.cpu().numpy() for k, v in model.state_dict().items()},
                        "feat_dim": X.shape[-1],
                        "window_frames": X.shape[1],
                        "hidden": args.hidden,
                        "labels": labels,
                        "mean": mean,
                        "std": std,
                        "val_acc": val_acc,
                        "val_punch_f1": punch_f1,
                    },
                    f,
                )

    print(f"\nbest punch_f1 {best_val:.3f}  →  {args.out}")


if __name__ == "__main__":
    main()
