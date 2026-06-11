#!/usr/bin/env bash
# batch_split_videos.sh — Run split_punch_video.py on all recordings.
#
# Usage:
#   chmod +x scripts/ml/batch_split_videos.sh
#   ./scripts/ml/batch_split_videos.sh
#
# Expected folder structure before running:
#   data/recordings/
#     S01_jab_left.mp4
#     S01_cross_right.mp4
#     S01_lead_hook_left.mp4
#     S01_rear_hook_right.mp4
#     S01_lead_uppercut_left.mp4
#     S01_rear_uppercut_right.mp4
#     S02_jab_left.mp4
#     ... etc
#
# File naming convention:
#   {subject_id}_{punch_type}_{hand}.mp4
#   e.g. S01_jab_left.mp4, S02_cross_right.mp4
#
# Clips will be written to:
#   data/clips/{subject_id}_{punch_type}_{hand}_{index}.mp4

set -euo pipefail

RECORDINGS_DIR="data/recordings"
OUT_DIR="data/clips"
SCRIPT="scripts/ml/split_punch_video.py"

# ── Map filename punch labels to CLI --label values ───────────────────────────
declare -A LABEL_MAP=(
  ["jab"]="jab"
  ["cross"]="cross"
  ["lead_hook"]="lead_hook"
  ["rear_hook"]="rear_hook"
  ["lead_uppercut"]="lead_uppercut"
  ["rear_uppercut"]="rear_uppercut"
)

# ── Process each .mp4 file in the recordings directory ────────────────────────
shopt -s nullglob
mp4_files=("$RECORDINGS_DIR"/*.mp4)

if [ ${#mp4_files[@]} -eq 0 ]; then
  echo "❌ No .mp4 files found in $RECORDINGS_DIR"
  echo "   Put your recordings there named as: S01_jab_left.mp4"
  exit 1
fi

echo "Found ${#mp4_files[@]} recording(s) to process."
echo ""

for video in "${mp4_files[@]}"; do
  filename=$(basename "$video" .mp4)

  # Parse: {subject}_{punch_type}_{hand}
  # Allow punch_type to contain underscores (lead_hook, rear_uppercut, etc.)
  IFS='_' read -ra parts <<< "$filename"
  subject="${parts[0]}"
  hand="${parts[-1]}"

  # Everything between subject and hand = punch label
  num_parts=${#parts[@]}
  punch_parts=("${parts[@]:1:$((num_parts - 2))}")
  punch_label=$(IFS='_'; echo "${punch_parts[*]}")

  # Validate hand
  if [[ "$hand" != "left" && "$hand" != "right" ]]; then
    echo "⚠️  Skipping $filename — filename must end with _left or _right"
    continue
  fi

  # Validate label
  if [[ -z "${LABEL_MAP[$punch_label]+_}" ]]; then
    echo "⚠️  Skipping $filename — unrecognised punch label '$punch_label'"
    echo "   Valid labels: jab, cross, lead_hook, rear_hook, lead_uppercut, rear_uppercut"
    continue
  fi

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Processing: $filename"
  echo "  Subject: $subject  |  Punch: $punch_label  |  Hand: $hand"
  echo ""

  uv run python "$SCRIPT" \
    --video "$video" \
    --label "$punch_label" \
    --hand "$hand" \
    --subject "$subject" \
    --out "$OUT_DIR" \
    --plot

  echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All recordings processed."
echo "   Clips saved to: $OUT_DIR"
echo ""

# Print clip count summary
total=$(find "$OUT_DIR" -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
echo "   Total clips: $total"
