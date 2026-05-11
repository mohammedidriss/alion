"""Temporal action classifier for boxing strike types.

Translates a window of pose frames into classified strikes:
jab, cross, hook, uppercut.

Two backends:
1. **Rule-based** (default, no training needed): improved heuristic using
   multi-frame trajectory analysis with angular velocity and arm geometry.
2. **Learned** (Phase 3+): LSTM/Transformer trained on labeled strike data.
   Loads from `data/ml/action_classifier_v1.pkl` when present.

The classifier is called *after* the punch detector fires. It receives the
pose history window around the detection and returns a `PunchType` label
with a confidence score.

This replaces `punch_type_heuristic.py` as the primary type classifier.
"""

from __future__ import annotations

import math
import pickle
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

from contracts import Hand, Landmark, PoseFrame, WorldLandmark

PunchType = Literal["jab", "cross", "hook", "uppercut"]

MODEL_PATH = Path("data/ml/action_classifier_v1.pkl")

# MediaPipe landmark indices.
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_ELBOW = 13
LM_RIGHT_ELBOW = 14
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Thresholds for the rule-based classifier.
HOOK_LATERAL_RATIO = 1.15
UPPERCUT_VERTICAL_RATIO = 1.3
BODY_ROTATION_THRESHOLD = 0.03  # radians of torso twist for cross detection
LOOKBACK_FRAMES = 8  # more frames than the old heuristic for better trajectory


class ActionClassifier:
    """Classifies detected punches into jab/cross/hook/uppercut.

    Attempts to load a trained model; falls back to rule-based classification.
    """

    def __init__(self, model_path: Path = MODEL_PATH) -> None:
        self._model: Any = None
        self._model_path = model_path
        self._backend: Literal["learned", "rules"] = "rules"
        self._try_load_model()

    def _try_load_model(self) -> None:
        if not self._model_path.exists():
            return
        try:
            with self._model_path.open("rb") as f:
                self._model = pickle.load(f)
            self._backend = "learned"
        except Exception:
            self._model = None

    @property
    def backend(self) -> str:
        return self._backend

    def classify(
        self,
        pose_history: Sequence[PoseFrame],
        hand: Hand,
        stance: str | None,
        *,
        lookback: int = LOOKBACK_FRAMES,
    ) -> tuple[PunchType, float]:
        """Classify a detected punch into a strike type.

        Returns (punch_type, confidence) where confidence is [0, 1].
        """
        if self._backend == "learned" and self._model is not None:
            return self._classify_learned(pose_history, hand, stance, lookback=lookback)
        return self._classify_rules(pose_history, hand, stance, lookback=lookback)

    # ------------------------------------------------------------------
    # Rule-based classifier (improved over punch_type_heuristic.py)
    # ------------------------------------------------------------------

    def _classify_rules(
        self,
        pose_history: Sequence[PoseFrame],
        hand: Hand,
        stance: str | None,
        *,
        lookback: int = LOOKBACK_FRAMES,
    ) -> tuple[PunchType, float]:
        """Multi-feature rule-based classification."""
        if len(pose_history) < 3:
            return self._fallback_straight(hand, stance)

        tail = list(pose_history[-lookback:])
        if len(tail) < 3:
            return self._fallback_straight(hand, stance)

        wrist_idx = LM_LEFT_WRIST if hand == "left" else LM_RIGHT_WRIST

        use_world = all(f.world_landmarks is not None for f in tail)

        # Extract trajectory.
        wrist_traj_raw = [self._xyz(f, wrist_idx, use_world) for f in tail]

        if any(p is None for p in wrist_traj_raw):
            return self._fallback_straight(hand, stance)

        wrist_traj: list[tuple[float, float, float]] = [
            cast("tuple[float, float, float]", p) for p in wrist_traj_raw
        ]

        # --- Feature 1: Net displacement vector ---
        start = wrist_traj[0]
        end = wrist_traj[-1]
        dx = end[0] - start[0]  # lateral
        dy = end[1] - start[1]  # vertical (negative = upward)
        dz = end[2] - start[2]  # depth

        abs_dx, abs_dy, abs_dz = abs(dx), abs(dy), abs(dz)

        # --- Feature 2: Path curvature (hook detection) ---
        curvature = self._path_curvature(wrist_traj)

        # --- Feature 3: Elbow angle at impact ---
        elbow_angle = self._elbow_angle_at_impact(tail[-1], hand, use_world)

        # --- Feature 4: Torso rotation (cross vs jab) ---
        torso_rotation = self._torso_rotation(tail, use_world)

        # --- Feature 5: Vertical velocity profile (uppercut) ---
        vert_velocity = self._vertical_velocity(wrist_traj, tail)

        # --- Decision tree with confidence scoring ---

        # UPPERCUT: strong upward motion + relatively straight arm path
        if (
            abs_dy >= UPPERCUT_VERTICAL_RATIO * max(abs_dx, abs_dz, 1e-6)
            and dy < 0
            and vert_velocity < -0.5
        ):
            conf = min(1.0, abs_dy / max(abs_dx + abs_dz, 1e-6) * 0.6)
            return ("uppercut", max(0.5, conf))

        # HOOK: high lateral motion OR high path curvature + bent elbow
        is_hook = False
        hook_conf = 0.0
        if abs_dx >= HOOK_LATERAL_RATIO * max(abs_dz, 1e-6):
            is_hook = True
            hook_conf = min(1.0, abs_dx / max(abs_dz, 1e-6) * 0.5)
        if curvature > 0.15 and elbow_angle is not None and elbow_angle < 140:
            is_hook = True
            hook_conf = max(hook_conf, min(1.0, curvature * 3.0))

        if is_hook:
            return ("hook", max(0.5, hook_conf))

        # STRAIGHT PUNCH: jab vs cross.
        # Cross: rear hand + significant torso rotation + higher velocity.
        is_lead = (stance == "orthodox" and hand == "left") or (
            stance == "southpaw" and hand == "right"
        )

        if stance in ("orthodox", "southpaw"):
            if not is_lead and abs(torso_rotation) > BODY_ROTATION_THRESHOLD:
                return ("cross", 0.75)
            if is_lead:
                return ("jab", 0.75)
            return ("cross" if not is_lead else "jab", 0.6)

        # Unknown stance: use torso rotation as tie-breaker.
        if abs(torso_rotation) > BODY_ROTATION_THRESHOLD * 1.5:
            return ("cross", 0.55)
        return ("jab", 0.55)

    # ------------------------------------------------------------------
    # Learned classifier (LSTM / Transformer)
    # ------------------------------------------------------------------

    def _classify_learned(
        self,
        pose_history: Sequence[PoseFrame],
        hand: Hand,
        stance: str | None,
        *,
        lookback: int = LOOKBACK_FRAMES,
    ) -> tuple[PunchType, float]:
        """Run the trained model on pose features."""
        try:
            import numpy as np
            import torch
        except ImportError:
            return self._classify_rules(pose_history, hand, stance, lookback=lookback)

        tail = list(pose_history[-lookback:])
        if len(tail) < 3 or self._model is None:
            return self._classify_rules(pose_history, hand, stance, lookback=lookback)

        labels: list[str] = self._model.get("labels", ["jab", "cross", "hook", "uppercut"])
        feat_dim = int(self._model.get("feat_dim", 264))
        window_frames = int(self._model.get("window_frames", 8))

        # Build feature matrix.
        features: list[list[float]] = []
        for f in tail[-window_frames:]:
            row: list[float] = []
            for lm in f.landmarks:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])
            if f.world_landmarks is not None:
                for wl in f.world_landmarks:
                    row.extend([wl.x, wl.y, wl.z, wl.visibility])
            else:
                row.extend([0.0] * (33 * 4))
            features.append(row[:feat_dim])

        # Pad if we have fewer frames than the window.
        while len(features) < window_frames:
            features.insert(0, features[0])

        arr = np.asarray(features, dtype=np.float32)
        mean = np.asarray(self._model.get("mean", np.zeros(feat_dim)), dtype=np.float32)
        std = np.asarray(self._model.get("std", np.ones(feat_dim)), dtype=np.float32) + 1e-6
        arr = (arr - mean) / std

        # Load model.
        from torch import nn

        hidden = int(self._model.get("hidden", 64))

        class ActionLSTM(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.lstm = nn.LSTM(feat_dim, hidden, num_layers=1, batch_first=True)
                self.head = nn.Linear(hidden, len(labels))

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                out, _ = self.lstm(x)
                return cast(torch.Tensor, self.head(out.mean(dim=1)))

        model = ActionLSTM()
        state = {k: torch.from_numpy(np.asarray(v)) for k, v in self._model["state_dict"].items()}
        model.load_state_dict(state)
        model.eval()

        with torch.no_grad():
            logits = model(torch.from_numpy(arr).unsqueeze(0))
            probs = torch.softmax(logits[0], dim=0).cpu().numpy()
            best_idx = int(np.argmax(probs))
            label = labels[best_idx]
            confidence = float(probs[best_idx])

        if label not in ("jab", "cross", "hook", "uppercut"):
            return self._classify_rules(pose_history, hand, stance, lookback=lookback)

        return (cast(PunchType, label), confidence)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _xyz(frame: PoseFrame, idx: int, use_world: bool) -> tuple[float, float, float] | None:
        if use_world and frame.world_landmarks is not None:
            wl = frame.world_landmarks[idx]
            if wl.visibility < 0.3:
                return None
            return (wl.x, wl.y, wl.z)
        lm = frame.landmarks[idx]
        if lm.visibility < 0.3:
            return None
        return (lm.x, lm.y, lm.z)

    @staticmethod
    def _path_curvature(traj: list[tuple[float, float, float]]) -> float:
        """Ratio of total path length to straight-line distance.

        A straight punch has curvature ~1.0. A hook has curvature > 1.2.
        """
        if len(traj) < 2:
            return 1.0
        total = 0.0
        for i in range(1, len(traj)):
            total += math.hypot(
                traj[i][0] - traj[i - 1][0],
                traj[i][1] - traj[i - 1][1],
                traj[i][2] - traj[i - 1][2],
            )
        straight = math.hypot(
            traj[-1][0] - traj[0][0],
            traj[-1][1] - traj[0][1],
            traj[-1][2] - traj[0][2],
        )
        if straight < 1e-6:
            return 1.0
        return total / straight

    @staticmethod
    def _elbow_angle_at_impact(frame: PoseFrame, hand: Hand, use_world: bool) -> float | None:
        """Elbow angle in degrees at the impact frame."""
        s_idx = LM_LEFT_SHOULDER if hand == "left" else LM_RIGHT_SHOULDER
        e_idx = LM_LEFT_ELBOW if hand == "left" else LM_RIGHT_ELBOW
        w_idx = LM_LEFT_WRIST if hand == "left" else LM_RIGHT_WRIST

        def _pt(idx: int) -> tuple[float, float, float] | None:
            if use_world and frame.world_landmarks is not None:
                wl = frame.world_landmarks[idx]
                return (wl.x, wl.y, wl.z) if wl.visibility >= 0.3 else None
            lm = frame.landmarks[idx]
            return (lm.x, lm.y, lm.z) if lm.visibility >= 0.3 else None

        s, e, w = _pt(s_idx), _pt(e_idx), _pt(w_idx)
        if s is None or e is None or w is None:
            return None

        v1 = (s[0] - e[0], s[1] - e[1], s[2] - e[2])
        v2 = (w[0] - e[0], w[1] - e[1], w[2] - e[2])
        dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
        m1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
        m2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
        if m1 < 1e-6 or m2 < 1e-6:
            return None
        cos_angle = max(-1.0, min(1.0, dot / (m1 * m2)))
        return math.degrees(math.acos(cos_angle))

    @staticmethod
    def _torso_rotation(frames: list[PoseFrame], use_world: bool) -> float:
        """Measure torso rotation between first and last frame.

        Positive = clockwise from above (left shoulder moves forward).
        Uses the angle between shoulder line and the camera plane.
        """
        if len(frames) < 2:
            return 0.0

        def shoulder_angle(f: PoseFrame) -> float | None:
            ls_lm: Landmark | WorldLandmark
            rs_lm: Landmark | WorldLandmark
            if use_world and f.world_landmarks is not None:
                ls_lm = f.world_landmarks[LM_LEFT_SHOULDER]
                rs_lm = f.world_landmarks[LM_RIGHT_SHOULDER]
            else:
                ls_lm = f.landmarks[LM_LEFT_SHOULDER]
                rs_lm = f.landmarks[LM_RIGHT_SHOULDER]
            if ls_lm.visibility < 0.3 or rs_lm.visibility < 0.3:
                return None
            dx = rs_lm.x - ls_lm.x
            dz = rs_lm.z - ls_lm.z
            return math.atan2(dz, dx)

        a0 = shoulder_angle(frames[0])
        a1 = shoulder_angle(frames[-1])
        if a0 is None or a1 is None:
            return 0.0
        return a1 - a0

    @staticmethod
    def _vertical_velocity(
        traj: list[tuple[float, float, float]],
        frames: list[PoseFrame],
    ) -> float:
        """Average vertical velocity (negative = upward). Units depend on
        whether world or image coords are used."""
        if len(traj) < 2 or len(frames) < 2:
            return 0.0
        dt = max(1e-3, (frames[-1].t_ms - frames[0].t_ms) / 1000.0)
        dy = traj[-1][1] - traj[0][1]
        return dy / dt

    @staticmethod
    def _fallback_straight(hand: Hand, stance: str | None) -> tuple[PunchType, float]:
        """When we can't classify, default to jab/cross by stance."""
        is_lead = (stance == "orthodox" and hand == "left") or (
            stance == "southpaw" and hand == "right"
        )
        if stance in ("orthodox", "southpaw"):
            return ("jab" if is_lead else "cross", 0.4)
        return ("jab", 0.4)


__all__ = ["ActionClassifier", "PunchType"]
