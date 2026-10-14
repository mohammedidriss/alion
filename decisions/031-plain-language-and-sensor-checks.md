# 031. Plain language in the menus, and a sensor check that says what to do

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

An external review found the app asks too much technical knowledge of an
ordinary boxer or coach: "IMU", "HRV", "Datasets" and "Bouts" as menu labels
with no explanation; the wrist-sensor page led with model names, Bluetooth
addresses and sampling rates; and "Check sensors" left a dot per wrist without
saying whether things were ready or what to do.

## Decision

- **Menu labels in plain words, each with a one-line explanation** (on hover and
  for screen readers): Heart rate (was HRV), Wrist sensors (IMU), Fights (Bouts),
  Research datasets (Datasets); the study, the AI model and every fighter tab
  say what they are. Page titles and the phone menu match. Addresses stay the
  same (`/hrv`, `/imu`, `/bouts`, `/datasets`); the technical term is kept in
  the explanation ("heart-rate variability (HRV)", "IMU").
- **The wrist-sensor check says what it found and what to do**: before a check,
  how to start one; after it, "Both sensors connected · checked 14:32" with
  "Ready — they start recording with the cameras", a charge warning below 20 %,
  or "Left wrist sensor not connected" with the steps to fix it (switch on, come
  closer, close whatever else holds it, check again) and the fact that a session
  still records without it. Each wrist reads Connected / Not connected and its
  battery.
- **Technical details behind a fold**: model, Bluetooth, sample rate, range,
  each unit's name and address, live rate, reading at rest and voltage; the
  terminal set-up commands likewise.

## Consequences

- Dashboard only.
