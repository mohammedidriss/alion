# 041. Rest cards: a facts ledger, three template cards, and a verifier for the model

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The RingsideIQ review board (14 Oct 2026) set two P0s for advice in the rest
between rounds: a deterministic claim-verification layer — no number or claim
reaches the corner unless it traces to sensor data — and a "3-card rule" for the
minute itself. Alion's advice so far was free text from the model, checked only
for medical wording (ADR-018, ADR-039). Heart rate in the rest wasn't stored at
all: the cameras pause, and beats in a pause were dropped.

## Decision

- **Rest heartbeats are kept** (`rest_hr_sample`, migration `b3d5f7a9c1e4`): a beat
  that arrives while the recording is paused is stored with the pause it fell in,
  where that pause sits on the clip's timeline, and how far into it.
  `rounds_export` gives each round's rest a recovery block — heart rate in the
  last 10 s before the bell, at 30 s and at 60 s, and the drops — from
  artifact-cleaned beats (ADR-040).
- **The facts ledger** (`api.services.rest_cards.build_facts`): after round N, what
  the sensors say — punches, punches per minute against the round before and
  round 1, each hand's share (lead/rear with the stance), punch types when a model
  named them, wrist force (a minimum when it clipped), heart rate in the round,
  recovery in the rest (so far, while it runs), and any stream that covered less
  than 80 % of the round. Each fact has an id, its numbers, the streams it came
  from, a quality (coverage, agreement) and an evidence level: always "thrown" —
  nothing here tells landed from blocked. A missing stream gives no fact, never 0.
- **Three template cards** (`template_cards`), always in the same places: ▲
  opportunity, ■ warning, ◆ recovery; each a fixed sentence from the facts it
  cites, with a confidence from the weakest cited fact. A slot with nothing to say
  says so ("Nothing new this round").
- **The model may phrase, never source** (`coach.verify`). `POST
  /sessions/{id}/rest_cards` asks the model (structured JSON, `generate_json`, 12 s)
  to rewrite the cards citing fact ids; each card passes nine gates or is dropped
  and its template stays: shape; citations exist and fit the slot (recovery cites
  heart facts only); every number is one a cited fact holds; rounds and hands match;
  up/down words match a fact's direction; no "landed/blocked/hit"; no guesses about
  the fighter's mind or body ("suggests confidence", "tired"); quality ≥ 0.5;
  safety terms. Every POST is recorded (`advice_gate`, kind `rest_cards`): the
  ledger's hash, the model's output, a verdict per card, what was shown.
- `GET /sessions/{id}/rest_cards` gives the ledger and template cards at once, no
  model. Coach-only study sessions get neither.

## Consequences

- `tests/integration/test_rest_cards.py`, `tests/unit/test_verify.py`.
- On a real 3-camera session with the local model (gemma3:4b), the verifier
  dropped a recovery card that cited the average heart rate but wrote the peak
  (97), and the inference gate was added after the model wrote "suggests growing
  confidence" about a punch-rate rise.
- Rest recovery needs the rest to be a pause: Rest Mode (ADR-043) pauses at each
  bell. Sessions recorded before this have no rest beats.
- V5's "100 % of displayed claims bound to facts" holds by construction; whether a
  sentence reads its fact correctly still needs a human audit on a sample.
