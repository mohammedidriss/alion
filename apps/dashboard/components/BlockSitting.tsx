"use client";

/**
 * One protocol block per take (ADR-013): after a block is saved, check it and move
 * on. The check (`/v2/takes/{id}/check`) says whether every camera's video arrived,
 * both wrist sensors recorded on the right wrists, the punches were there, and the
 * heart rate came in. In a sitting, a block that passes leads straight to the next
 * block's take — its page connects the phones and sensors during the rest and then
 * starts by itself. A block that fails stops the sitting and offers Redo, so a
 * mistake costs one block (about a minute), not the whole protocol.
 */

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type ProtocolBlockSpec, type Take, type TakeCheck } from "@/lib/api";
import { say } from "@/lib/cues";

const PREFS_KEY = "alion.autoProtocol"; // AutoProtocol's pace / rest settings

function restSeconds(): number {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}");
    return Number.isFinite(p.restS) ? Math.max(0, p.restS) : 20;
  } catch {
    return 20;
  }
}

/** The take page for a block, in sitting mode: start by itself after `restUntil`. */
export function blockHref(datasetId: string, takeId: string, restUntil?: number): string {
  const q = restUntil ? `?sitting=1&rest=${Math.round(restUntil)}` : "?sitting=1";
  return `/datasets/${datasetId}/takes/${takeId}${q}`;
}

export function BlockSitting({
  take,
  plan,
  sitting,
}: {
  take: Take;
  plan: ProtocolBlockSpec[];
  sitting: boolean; // keep going block after block
}) {
  const router = useRouter();
  const [check, setCheck] = useState<TakeCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const moved = useRef(false);

  const idx = plan.findIndex((s) => s.key === take.block);
  const next = idx >= 0 ? plan[idx + 1] : undefined;
  const spoken = (s: ProtocolBlockSpec) => (s.kind === "combo" && s.callout) || s.title;

  // The check is ready once the take is saved; poll until then.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const c = await api.takeCheck(take.id).catch(() => null);
      if (!alive) return;
      if (c?.ready) setCheck(c);
      else timer = setTimeout(poll, 1500);
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [take.id]);

  const goTo = async (block: ProtocolBlockSpec | undefined, rest: boolean) => {
    if (!block) return;
    setBusy(true);
    try {
      const t = await api.createTake(take.dataset_id, take.fighter_id, block.key);
      const restS = rest ? restSeconds() : 0;
      if (rest && restS > 0) say(`Rest. Next, ${spoken(block)}.`);
      router.replace(blockHref(take.dataset_id, t.id, rest ? Date.now() + restS * 1000 : undefined));
    } catch {
      setBusy(false);
    }
  };

  const redo = async () => {
    const spec = plan[idx];
    if (!spec) return;
    setBusy(true);
    await api.deleteTake(take.id).catch(() => {});
    await goTo(spec, false);
  };

  // In a sitting, a block that passed leads straight on.
  useEffect(() => {
    if (!sitting || !check?.ok || moved.current) return;
    moved.current = true;
    if (next) void goTo(next, true);
    else say("All blocks recorded. Well done.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sitting, check]);

  // A failed block stops the sitting — say so, the coach may be across the room.
  const announced = useRef(false);
  useEffect(() => {
    if (!sitting || !check || check.ok || announced.current) return;
    announced.current = true;
    say("Check the block. Something needs a redo.");
  }, [sitting, check]);

  const title = plan[idx]?.title ?? take.block ?? "Block";
  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">
          {title} — {check ? (check.ok ? "good" : "needs a redo") : "checking…"}
        </h2>
        {idx >= 0 && (
          <span className="text-xs text-neutral-500">
            block {idx + 1} of {plan.length}
          </span>
        )}
      </div>

      {!check ? (
        <p className="animate-pulse text-sm text-sky-300/90">
          Saving and checking the block — keep the phones open…
        </p>
      ) : (
        <ul className="space-y-1 text-sm">
          {check.checks.map((c, i) => (
            <li key={`${c.key}-${i}`} className="flex gap-2">
              <span
                className={
                  c.level === "ok"
                    ? "text-emerald-400"
                    : c.level === "warn"
                      ? "text-amber-300"
                      : "text-red-400"
                }
              >
                {c.level === "ok" ? "✓" : c.level === "warn" ? "⚠" : "✗"}
              </span>
              <span className={c.level === "fail" ? "text-red-200" : "text-neutral-300"}>{c.text}</span>
            </li>
          ))}
        </ul>
      )}

      {check && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {check.ok && sitting && next ? (
            <span className="text-sm text-neutral-400">Next: {next.title} — opening…</span>
          ) : (
            <>
              {next && (
                <button
                  onClick={() => goTo(next, true)}
                  disabled={busy}
                  className={`rounded-xl px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
                    check.ok
                      ? "bg-emerald-500 text-black hover:bg-emerald-400"
                      : "border border-white/15 text-neutral-200 hover:bg-white/5"
                  }`}
                >
                  {check.ok ? `▶ Next: ${next.title}` : `Keep it and go on to ${next.title}`}
                </button>
              )}
              {!check.ok && (
                <button
                  onClick={redo}
                  disabled={busy}
                  className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50"
                  title="Deletes this take and records the block again"
                >
                  ↺ Redo {title}
                </button>
              )}
              {!next && check.ok && (
                <span className="text-sm text-emerald-300">All blocks recorded ✓</span>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
