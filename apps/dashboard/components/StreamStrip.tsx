"use client";

/**
 * The stream status strip (ADR-042): one shape per live stream — each camera ■,
 * each wrist ●, the chest strap ♥ — coloured and worded by its health. A shape
 * says the same as its colour (OK, slow, lost, coming back), so it reads at a
 * glance and without colour vision. Details are in the tooltip only.
 */

import { useEffect, useState } from "react";
import { api, type StreamHealth } from "@/lib/api";

const SHAPE: Record<StreamHealth["kind"], string> = { camera: "■", wrist: "●", heart: "♥" };
const WORD: Record<StreamHealth["state"], string> = {
  ok: "OK",
  degraded: "slow",
  lost: "lost",
  recovering: "back",
  off: "off",
};

export function streamTone(state: StreamHealth["state"], light = false): string {
  if (light) {
    return state === "ok"
      ? "border-emerald-700 text-emerald-900"
      : state === "degraded"
        ? "border-amber-600 text-amber-900"
        : state === "recovering"
          ? "border-sky-700 text-sky-900"
          : state === "lost"
            ? "border-red-700 bg-red-50 text-red-800"
            : "border-neutral-400 text-neutral-600";
  }
  return state === "ok"
    ? "border-emerald-500/40 text-emerald-300"
    : state === "degraded"
      ? "border-amber-500/50 text-amber-300"
      : state === "recovering"
        ? "border-sky-400/50 text-sky-300"
        : state === "lost"
          ? "border-red-500/60 bg-red-950/40 text-red-300"
          : "border-white/15 text-neutral-500";
}

export function useStreams(sessionId: string | undefined, active: boolean): StreamHealth[] {
  const [streams, setStreams] = useState<StreamHealth[]>([]);
  useEffect(() => {
    if (!sessionId || !active) {
      setStreams([]);
      return;
    }
    let alive = true;
    const poll = () =>
      api
        .streams(sessionId)
        .then((s) => alive && setStreams(s))
        .catch(() => {});
    poll();
    const id = setInterval(poll, 1500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId, active]);
  return streams;
}

export function StreamStrip({
  streams,
  light = false,
  large = false,
}: {
  streams: StreamHealth[];
  light?: boolean;
  large?: boolean;
}) {
  if (streams.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="status" aria-label="Sensor streams">
      {streams.map((s) => (
        <span
          key={s.key}
          title={`${s.label}: ${WORD[s.state]}${s.reason ? ` — ${s.reason}` : ""}`}
          className={`inline-flex items-center gap-1 rounded-md border font-medium ${streamTone(s.state, light)} ${
            large ? "px-2 py-1 text-sm" : "px-1.5 py-0.5 text-[11px]"
          }`}
        >
          <span aria-hidden>{SHAPE[s.kind]}</span>
          <span>{s.label}</span>
          {s.state !== "ok" && <span className="font-semibold uppercase">{WORD[s.state]}</span>}
        </span>
      ))}
    </div>
  );
}
