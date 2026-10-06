"use client";

/**
 * One category (protocol block) per take (ADR-013): once the take is saved, check
 * it — did every camera's video arrive, did both wrist sensors record on the right
 * wrists, were the punches there, did the heart rate come in
 * (`/v2/takes/{id}/check`) — and offer the next step: record another take of the
 * same category, redo this one, or go back to the categories. Nothing moves on by
 * itself: the coach picks each category.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type ProtocolBlockSpec, type Take, type TakeCheck } from "@/lib/api";
import { say } from "@/lib/cues";

export function BlockResult({ take, plan }: { take: Take; plan: ProtocolBlockSpec[] }) {
  const router = useRouter();
  const [check, setCheck] = useState<TakeCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const spec = plan.find((s) => s.key === take.block);
  const title = spec?.title ?? take.block ?? "Take";

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

  // Say how it went — the fighter may be across the room from the laptop.
  const announced = useRef(false);
  useEffect(() => {
    if (!check || announced.current) return;
    announced.current = true;
    say(check.ok ? `${title} saved.` : "Check the recording. Something needs a redo.");
  }, [check, title]);

  /** A new take of this category; `replace` deletes this one first (Redo). */
  const recordAgain = async (replace: boolean) => {
    setBusy(true);
    try {
      if (replace) await api.deleteTake(take.id);
      const t = await api.createTake(take.dataset_id, take.fighter_id, take.block);
      router.replace(`/datasets/${take.dataset_id}/takes/${t.id}`);
    } catch {
      setBusy(false);
    }
  };

  return (
    <section className="card space-y-3">
      <h2 className="text-base font-semibold">
        {title} — {check ? (check.ok ? "saved ✓" : "needs a redo") : "checking…"}
      </h2>

      {!check ? (
        <p className="animate-pulse text-sm text-sky-300/90">
          Saving and checking — keep the phones open…
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
          {!check.ok && (
            <button
              onClick={() => recordAgain(true)}
              disabled={busy}
              className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50"
              title="Deletes this take and records the category again"
            >
              ↺ Redo {title}
            </button>
          )}
          <button
            onClick={() => recordAgain(false)}
            disabled={busy}
            className={`rounded-xl px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
              check.ok
                ? "bg-red-600 text-white hover:bg-red-500"
                : "border border-white/15 text-neutral-200 hover:bg-white/5"
            }`}
          >
            ● Record another {title}
          </button>
          <Link
            href={`/datasets/${take.dataset_id}`}
            className="rounded-xl border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
          >
            ← Categories
          </Link>
        </div>
      )}
    </section>
  );
}
