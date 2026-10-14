"use client";

/**
 * The between-rounds debrief (ADR-043), after the session: for each rest, the
 * coach first writes what they saw in the round, then reveals the three cards the
 * sensors would have shown, with their evidence, and marks each noted or not.
 *
 * Committing a read before seeing the system's is the review board's answer to
 * over-reliance (cognitive forcing) — too slow for the real minute, right for the
 * debrief. Everything is logged against the facts it was shown with.
 */

import { useCallback, useEffect, useState } from "react";
import { RestMode } from "@/components/RestMode";
import { api, type CardFeedback, type RestCards, type RoundsExportResponse } from "@/lib/api";

function errorText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/^(\d{3}) ([\s\S]*)$/);
  try {
    return m ? String(JSON.parse(m[2]).detail ?? raw) : raw;
  } catch {
    return raw;
  }
}

export function RestDebrief({ sessionId }: { sessionId: string }) {
  const [ex, setEx] = useState<RoundsExportResponse | null>(null);
  const [logged, setLogged] = useState<CardFeedback[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [read, setRead] = useState<Record<number, string>>({});
  const [cards, setCards] = useState<Record<number, RestCards>>({});
  const [err, setErr] = useState<string | null>(null);
  const [full, setFull] = useState<number | null>(null);

  const load = useCallback(() => {
    api.cardFeedback(sessionId).then(setLogged).catch(() => {});
  }, [sessionId]);
  useEffect(() => {
    api.roundsExport(sessionId).then(setEx).catch(() => {});
    load();
  }, [sessionId, load]);

  if (!ex || ex.study_condition === "coach_only") return null;
  // Rests that follow a round with something in it.
  const rests = ex.rounds
    .slice(0, -1)
    .filter((r) => r.punch_count > 0 || r.hrv.mean_hr_bpm != null)
    .map((r) => r.round_number);
  if (rests.length === 0) return null;

  const reveal = async (k: number) => {
    setErr(null);
    const text = (read[k] ?? "").trim();
    try {
      if (text) {
        await api.addCardFeedback(sessionId, { after_round: k, slot: "own_read", action: "own_read", note: text });
      }
      const d = await api.restCards(sessionId, k);
      setCards((c) => ({ ...c, [k]: d }));
      load();
    } catch (e) {
      setErr(errorText(e));
    }
  };

  return (
    <section className="card space-y-3">
      <div>
        <h2 className="text-base font-semibold">Between rounds — your read first</h2>
        <p className="text-xs text-neutral-400">
          For each rest: write what you saw in the round, then show the cards the sensors would have
          given you. Mark each one noted or not — it tells us when the cards help and when they don&apos;t.
        </p>
      </div>
      {err && <p className="text-sm text-red-300">{err}</p>}
      <ul className="space-y-2">
        {rests.map((k) => {
          const mine = logged.filter((f) => f.after_round === k);
          const own = mine.find((f) => f.action === "own_read");
          const shown = cards[k];
          return (
            <li key={k} className="rounded-xl border border-white/10 p-3">
              <button
                onClick={() => setOpen(open === k ? null : k)}
                className="flex w-full items-center justify-between text-left text-sm font-medium text-neutral-100"
                aria-expanded={open === k}
              >
                <span>After round {k}</span>
                <span className="text-xs text-neutral-400">
                  {own ? "your read logged" : "not reviewed"}
                  {mine.some((f) => f.action !== "own_read") &&
                    ` · ${mine.filter((f) => f.action !== "own_read").length} card${mine.filter((f) => f.action !== "own_read").length === 1 ? "" : "s"} marked`}
                </span>
              </button>
              {open === k && (
                <div className="mt-2 space-y-2">
                  {!shown ? (
                    <>
                      <textarea
                        id={`own-read-${k}`}
                        value={read[k] ?? own?.note ?? ""}
                        onChange={(e) => setRead((r) => ({ ...r, [k]: e.target.value }))}
                        rows={2}
                        maxLength={1000}
                        placeholder={`What did you see in round ${k}? What would you have told the fighter?`}
                        className="w-full rounded-xl border border-white/10 bg-black/30 p-2 text-sm outline-none focus:border-emerald-500/50"
                      />
                      <button
                        onClick={() => void reveal(k)}
                        className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
                      >
                        {(read[k] ?? "").trim() ? "Save my read and show the cards" : "Show the cards"}
                      </button>
                    </>
                  ) : (
                    <>
                      {own?.note && (
                        <p className="text-sm text-neutral-300">
                          <span className="text-neutral-500">Your read:</span> {own.note}
                        </p>
                      )}
                      <ul className="grid gap-2 sm:grid-cols-3">
                        {shown.cards.map((c) => {
                          const mark = mine.find((f) => f.slot === c.slot && f.action !== "own_read");
                          return (
                            <li key={c.slot} className="rounded-lg border border-white/10 p-2 text-sm">
                              <p className="text-[11px] uppercase tracking-wide text-neutral-400">
                                {c.shape} {c.slot}
                              </p>
                              <p className="font-semibold text-neutral-100">{c.headline}</p>
                              {c.number && <p className="font-mono text-lg tabular-nums">{c.number}</p>}
                              {c.context && <p className="text-xs text-neutral-400">{c.context}</p>}
                              {c.fact_ids.length > 0 && (
                                <div className="mt-1 flex gap-1.5">
                                  {(["noted", "dismissed"] as const).map((a) => (
                                    <button
                                      key={a}
                                      disabled={!!mark}
                                      onClick={() =>
                                        void api
                                          .addCardFeedback(sessionId, {
                                            after_round: k,
                                            slot: c.slot,
                                            action: a,
                                            headline: c.headline,
                                            fact_ids: c.fact_ids,
                                            facts_sha256: shown.facts_sha256,
                                          })
                                          .then(load)
                                      }
                                      className={`rounded-md border px-2 py-0.5 text-xs ${
                                        mark?.action === a
                                          ? "border-emerald-500/60 text-emerald-300"
                                          : "border-white/15 text-neutral-300 hover:bg-white/5"
                                      } disabled:cursor-default`}
                                    >
                                      {a === "noted" ? "✓ Useful" : "✕ Not useful"}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                      <button
                        onClick={() => setFull(k)}
                        className="text-xs text-emerald-400 hover:underline"
                      >
                        Open as the corner saw it, with the evidence
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {full != null && (
        <RestMode
          sessionId={sessionId}
          afterRound={full}
          roundCount={ex.round_count}
          restS={ex.rest_duration_s}
          startedAt={Date.now()}
          streams={[]}
          live={false}
          onBackToLive={() => setFull(null)}
        />
      )}
    </section>
  );
}
