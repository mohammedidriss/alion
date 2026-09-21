"use client";

/**
 * Bout detail + capture (ADR-011). One page for the whole fight: a shared scoreboard
 * and round timer, one Start fight / Pause / Stop driving both corners together, and
 * a live punch count per fighter — via <BoutCapture>. Each corner is still its own
 * single-fighter session underneath. Set the result when the fight is done.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { BoutCapture } from "@/components/BoutCapture";
import { api, type Bout, type BoutOutcome, type Fighter, type Session } from "@/lib/api";

export default function BoutDetailPage() {
  const params = useParams();
  const id = String(params.id);
  const [bout, setBout] = useState<Bout | null>(null);
  const [parts, setParts] = useState<Session[]>([]);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getBout(id).then(setBout).catch((e) => setErr(String(e)));
    api.boutParticipants(id).then(setParts).catch(() => {});
    api.listFighters().then(setFighters).catch(() => {});
  }, [id]);

  if (err) return <div className="p-6 text-sm text-red-300">{err}</div>;
  if (!bout) return <div className="p-6 text-sm text-neutral-500">Loading…</div>;

  const red = parts.find((s) => s.corner === "red");
  const blue = parts.find((s) => s.corner === "blue");
  const nameOf = (fid?: string) =>
    fighters.find((f) => f.id === fid)?.name ?? (fid ? fid.slice(0, 8) : "—");

  const setResult = async (winner: BoutOutcome) => {
    const method =
      winner === "draw" ? null : window.prompt("Method? (e.g. KO, TKO, decision)") || null;
    const updated = await api.setBoutResult(id, winner, method).catch(() => null);
    if (updated) setBout(updated);
  };

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <Link href="/bouts" className="hover:underline">
          Bouts
        </Link>
        <span>/</span>
        <span className="text-neutral-200">{bout.label || "Untitled bout"}</span>
      </div>

      <header>
        <h1 className="text-2xl font-semibold">{bout.label || "Untitled bout"}</h1>
        <p className="text-sm text-neutral-400">
          {new Date(bout.scheduled_at).toLocaleString()} · {bout.round_count}×
          {Math.round(bout.round_duration_s / 60)}min · rest {bout.rest_duration_s}s
        </p>
        {bout.winner_corner && (
          <p className="mt-1 text-sm font-medium text-neutral-200">
            Result: {bout.winner_corner === "draw" ? "Draw" : `${bout.winner_corner} corner`}
            {bout.result_method ? ` · ${bout.result_method}` : ""}
          </p>
        )}
      </header>

      {red && blue ? (
        <BoutCapture
          bout={bout}
          red={red}
          blue={blue}
          redName={nameOf(red.fighter_id)}
          blueName={nameOf(blue.fighter_id)}
        />
      ) : (
        <p className="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-4 text-sm text-amber-200">
          This bout is missing a corner assignment — both a red and a blue fighter are needed to
          capture.
        </p>
      )}

      <div className="card space-y-3">
        <h2 className="text-lg font-semibold">Result</h2>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setResult("red")}
            className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
          >
            Red wins
          </button>
          <button
            onClick={() => setResult("blue")}
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Blue wins
          </button>
          <button
            onClick={() => setResult("draw")}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-sm hover:bg-white/5"
          >
            Draw
          </button>
        </div>
      </div>
    </div>
  );
}
