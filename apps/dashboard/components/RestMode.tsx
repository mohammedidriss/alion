"use client";

/**
 * Rest Mode (ADR-043): the corner's screen for the minute between rounds.
 *
 * From the RingsideIQ review board's blueprint: three cards in fixed places
 * (▲ opportunity, ■ warning, ◆ recovery), each one headline, one number and the
 * streams it came from, readable in a two-second glance from the stool. One tap on
 * "Evidence" raises a drawer over the lower half with the facts behind the card,
 * without leaving the screen. Light, high-contrast and large by default (ring
 * lights); dark on request. The countdown runs the rest; at 10 s it says so and at
 * 0 the recording resumes.
 *
 * The cards come from the facts ledger at once; a model's phrasing replaces a card
 * only where every number and word checked out on the server. They describe what
 * happened — the coach decides what it means.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { StreamStrip } from "@/components/StreamStrip";
import { api, type RestCard, type RestCards, type RestFact, type StreamHealth } from "@/lib/api";
import { say } from "@/lib/cues";

const LABEL: Record<RestCard["slot"], string> = {
  opportunity: "Opportunity",
  warning: "Warning",
  recovery: "Recovery",
};

function errorText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/^(\d{3}) ([\s\S]*)$/);
  try {
    return m ? String(JSON.parse(m[2]).detail ?? raw) : raw;
  } catch {
    return raw;
  }
}

function clock(s: number): string {
  const v = Math.max(0, Math.ceil(s));
  return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
}

export function RestMode({
  sessionId,
  afterRound,
  roundCount,
  restS,
  startedAt,
  streams,
  live = true,
  onBackToLive,
}: {
  sessionId: string;
  afterRound: number;
  roundCount: number;
  restS: number;
  startedAt: number; // when the rest began (ms, Date.now clock)
  streams: StreamHealth[];
  live?: boolean;
  onBackToLive: () => void;
}) {
  const [data, setData] = useState<RestCards | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<RestCard | null>(null);
  const [done, setDone] = useState<Record<string, "noted" | "dismissed">>({});
  const [light, setLight] = useState(true);
  const [now, setNow] = useState(Date.now());
  const warned = useRef(false);
  const finished = useRef(false);
  const modelCards = useRef<Record<string, RestCard>>({});

  // Template cards at once; then the model's verified phrasing, once.
  useEffect(() => {
    let alive = true;
    api
      .restCards(sessionId, afterRound, live)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setErr(errorText(e)));
    api
      .phraseRestCards(sessionId, afterRound, live)
      .then((d) => {
        if (!alive) return;
        for (const c of d.cards) if (c.source === "model") modelCards.current[c.slot] = c;
        setData((prev) =>
          prev ? { ...prev, cards: prev.cards.map((c) => modelCards.current[c.slot] ?? c) } : d,
        );
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [sessionId, afterRound, live]);

  // Recovery keeps counting while the rest runs: refresh the ledger every 10 s,
  // keeping any card the model phrased.
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => {
      api
        .restCards(sessionId, afterRound, true)
        .then((d) => setData({ ...d, cards: d.cards.map((c) => modelCards.current[c.slot] ?? c) }))
        .catch(() => {});
    }, 10_000);
    return () => clearInterval(id);
  }, [sessionId, afterRound, live]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);

  const left = restS - (now - startedAt) / 1000;
  const back = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    onBackToLive();
  }, [onBackToLive]);

  useEffect(() => {
    if (!live) return;
    if (left <= 10 && !warned.current) {
      warned.current = true;
      say("Ten seconds");
    }
    if (left <= 0) back();
  }, [left, live, back]);

  const feedback = async (card: RestCard, action: "noted" | "dismissed") => {
    setDone((d) => ({ ...d, [card.slot]: action }));
    await api
      .addCardFeedback(sessionId, {
        after_round: afterRound,
        slot: card.slot,
        action,
        headline: card.headline,
        fact_ids: card.fact_ids,
        facts_sha256: data?.facts_sha256 ?? null,
      })
      .catch(() => {});
  };

  const facts = new Map((data?.facts ?? []).map((f) => [f.id, f]));
  const t = light
    ? {
        page: "bg-[#f7f7f4] text-[#111316]",
        card: "border-[#111316]/15 bg-white",
        muted: "text-[#4a4f57]",
        btn: "border-[#111316]/25 text-[#111316] hover:bg-[#111316]/5",
        bar: "bg-[#111316]/10",
        fill: "bg-[#111316]",
        accent: { opportunity: "text-emerald-800", warning: "text-red-700", recovery: "text-sky-800" },
      }
    : {
        page: "bg-[#0b0d10] text-[#eef0f3]",
        card: "border-white/15 bg-[#14171c]",
        muted: "text-[#a3a9b4]",
        btn: "border-white/25 text-[#eef0f3] hover:bg-white/10",
        bar: "bg-white/10",
        fill: "bg-[#eef0f3]",
        accent: { opportunity: "text-emerald-300", warning: "text-red-300", recovery: "text-sky-300" },
      };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Rest after round ${afterRound}`}
      className={`fixed inset-0 z-50 flex flex-col overflow-y-auto ${t.page}`}
      style={{ paddingTop: "env(safe-area-inset-top, 0px)", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      {/* Top bar: state, countdown, streams */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4 sm:px-6">
        <div className="flex items-baseline gap-4">
          <span className="text-xl font-bold uppercase tracking-wide sm:text-2xl">
            Round {afterRound} · Rest
          </span>
          {live && (
            <span className="font-mono text-4xl font-bold tabular-nums sm:text-5xl" aria-live="polite">
              {clock(left)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <StreamStrip streams={streams} light={light} large />
          <button
            onClick={() => setLight((v) => !v)}
            className={`min-h-[44px] rounded-lg border px-3 text-sm ${t.btn}`}
          >
            {light ? "Dark" : "Light"}
          </button>
        </div>
      </div>
      {live && (
        <div className={`mx-4 mt-3 h-2 overflow-hidden rounded-full sm:mx-6 ${t.bar}`}>
          <div
            className={`h-full ${t.fill}`}
            style={{ width: `${Math.max(0, Math.min(100, (left / restS) * 100))}%` }}
          />
        </div>
      )}

      {/* Three cards, always in the same places */}
      <div className="grid flex-1 gap-3 px-4 py-4 sm:px-6 md:grid-cols-3">
        {err && <p className="text-lg md:col-span-3">{err}</p>}
        {!data && !err && <p className={`text-lg ${t.muted} md:col-span-3`}>Reading the round…</p>}
        {data?.cards.map((c) => (
          <div
            key={c.slot}
            className={`flex min-w-0 flex-col justify-between gap-3 rounded-2xl border-2 p-4 sm:p-5 ${t.card} ${
              done[c.slot] === "dismissed" ? "opacity-40" : ""
            }`}
          >
            <div className="space-y-2">
              <div className={`flex items-center gap-2 text-base font-bold uppercase tracking-wider ${t.accent[c.slot]}`}>
                <span aria-hidden className="text-2xl">
                  {c.shape}
                </span>
                {LABEL[c.slot]}
              </div>
              <p className="text-2xl font-bold leading-tight sm:text-3xl" style={{ textWrap: "balance" }}>
                {c.headline}
              </p>
              {c.number && <p className="font-mono text-5xl font-bold tabular-nums sm:text-6xl">{c.number}</p>}
              {c.context && <p className={`text-lg ${t.muted}`}>{c.context}</p>}
            </div>
            {c.fact_ids.length > 0 && (
              <div className="space-y-2">
                <p className={`text-sm ${t.muted}`}>
                  <span aria-label={`confidence ${c.confidence} of 4`}>
                    {"●".repeat(c.confidence)}
                    {"○".repeat(4 - c.confidence)}
                  </span>{" "}
                  {c.streams.join(" + ")}
                  {c.source === "model" && " · phrased by the model, checked"}
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setDrawer(c)}
                    className={`min-h-[56px] flex-1 rounded-xl border-2 px-4 text-lg font-semibold ${t.btn}`}
                  >
                    Evidence ▾
                  </button>
                  <button
                    onClick={() => void feedback(c, "noted")}
                    aria-pressed={done[c.slot] === "noted"}
                    className={`min-h-[56px] min-w-[64px] rounded-xl border-2 px-4 text-lg font-semibold ${t.btn} ${
                      done[c.slot] === "noted" ? "ring-2 ring-emerald-600" : ""
                    }`}
                    title="Noted"
                  >
                    ✓
                  </button>
                  <button
                    onClick={() => void feedback(c, "dismissed")}
                    aria-pressed={done[c.slot] === "dismissed"}
                    className={`min-h-[56px] min-w-[64px] rounded-xl border-2 px-4 text-lg font-semibold ${t.btn}`}
                    title="Dismiss"
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer: back to live */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-4 sm:px-6">
        <p className={`text-sm ${t.muted}`}>
          What the sensors counted — punches thrown, not landed. Training information, not medical
          advice: the coach decides.
        </p>
        <button
          onClick={back}
          className="min-h-[56px] rounded-xl bg-emerald-600 px-6 text-lg font-bold text-white hover:bg-emerald-500"
        >
          {live
            ? `Back to live${afterRound < roundCount ? ` · round ${afterRound + 1}` : ""}`
            : "Close"}
        </button>
      </div>

      {/* The evidence drawer: over the lower half, never a new screen */}
      {drawer && (
        <div className="fixed inset-0 z-[60] flex flex-col justify-end" onClick={() => setDrawer(null)}>
          <div
            className={`max-h-[60vh] overflow-y-auto rounded-t-2xl border-t-2 p-4 shadow-2xl sm:p-6 ${t.card}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl font-bold">Evidence · {drawer.headline}</h2>
              <button
                onClick={() => setDrawer(null)}
                className={`min-h-[48px] rounded-xl border-2 px-4 text-base font-semibold ${t.btn}`}
              >
                Close ▾
              </button>
            </div>
            <ul className="mt-3 space-y-2">
              {drawer.fact_ids
                .map((id) => facts.get(id))
                .filter((f): f is RestFact => !!f)
                .map((f) => (
                  <li key={f.id} className="text-base">
                    <span className="font-mono text-sm">{f.id}</span> · {f.text}
                    <span className={`block text-sm ${t.muted}`}>
                      {f.streams.join(" + ")} · quality {Math.round(f.quality * 100)}% · evidence:{" "}
                      {f.evidence}
                    </span>
                  </li>
                ))}
            </ul>
            <p className={`mt-3 text-xs ${t.muted}`}>
              Facts {data?.facts_sha256.slice(0, 12)} · {drawer.source === "model" ? "phrased by the model and checked against these facts" : "written from these facts by fixed rules"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
