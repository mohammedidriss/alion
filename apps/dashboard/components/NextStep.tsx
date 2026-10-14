"use client";

/**
 * One clear next step at the top of a home page (ADR-031): what to do now, as a
 * single primary action, and at most one other. Used on the fighter page, a
 * coach's own page (`CoachNextStep`) and an empty gym's dashboard.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type StudyMe } from "@/lib/api";

type Action = { label: string; href?: string; onClick?: () => void | Promise<void> };

export function NextStep({
  title,
  text,
  primary,
  secondary,
}: {
  title: string;
  text: string;
  primary: Action;
  secondary?: Action | null;
}) {
  const [busy, setBusy] = useState(false);
  const button =
    "inline-flex items-center rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50";
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/[0.06] p-4">
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">Next step</p>
        <h2 className="text-lg font-semibold text-neutral-50">{title}</h2>
        <p className="text-sm text-neutral-300">{text}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {secondary &&
          (secondary.href ? (
            <Link href={secondary.href} className="text-sm text-emerald-300 hover:underline">
              {secondary.label}
            </Link>
          ) : (
            <button onClick={() => void secondary.onClick?.()} className="text-sm text-emerald-300 hover:underline">
              {secondary.label}
            </button>
          ))}
        {primary.href ? (
          <Link href={primary.href} className={button}>
            {primary.label} →
          </Link>
        ) : (
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await primary.onClick?.();
              } finally {
                setBusy(false);
              }
            }}
            className={button}
          >
            {busy ? "Opening…" : `${primary.label} →`}
          </button>
        )}
      </div>
    </section>
  );
}

/** A coach's own page: the study while there's a step waiting, else a session. */
export function CoachNextStep() {
  const [study, setStudy] = useState<StudyMe | null>(null);
  useEffect(() => {
    api
      .studyMe()
      .then(setStudy)
      .catch(() => setStudy(null)); // not enrolled
  }, []);
  if (study && study.ready && study.step.kind !== "done") {
    return (
      <NextStep
        title="Continue the advisory review study"
        text={`${study.step.label} — ${study.decisions} of ${study.total} advisories reviewed.`}
        primary={{ label: "Continue the study", href: "/study" }}
        secondary={{ label: "Start a training session", href: "/sessions/new" }}
      />
    );
  }
  return (
    <NextStep
      title="Start a training session"
      text="Pick a fighter, connect the cameras and sensors, and record when everyone's ready."
      primary={{ label: "Start a training session", href: "/sessions/new" }}
    />
  );
}
