/** What a dataset protocol is for, in words — shown on every dataset recorded with it
 * (ADR-057). The methodology lives in docs/studies/. */
export const PROTOCOL_PURPOSE: Record<string, string> = {
  "rq2-v1":
    "Ground truth for research question 2 — does the platform detect punches (F1 ≥ 0.80), name their type (≥ 0.70) and time them? The fighter throws fixed blocks (30 jabs, 30 crosses, …); the wrist sensors time every punch, so each take comes out labelled.",
};
