"use client";

import { useEffect, useState } from "react";
import { ImuSensorsPanel } from "@/components/ImuSensors";
import { SessionRecordingsCard } from "@/components/SessionRecordingsCard";
import { api, type Fighter } from "@/lib/api";

export default function ImuTab({ params }: { params: { id: string } }) {
  const [fighter, setFighter] = useState<Fighter | null>(null);

  useEffect(() => {
    api.getFighter(params.id).then(setFighter).catch(() => setFighter(null));
  }, [params.id]);

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header>
        <h1 className="text-2xl font-semibold">IMU</h1>
        <p className="text-sm text-neutral-400">
          Wrist-worn inertial sensors: acceleration and rotation of each fist, on the same
          timeline as the video.
        </p>
      </header>

      {fighter && <ImuSensorsPanel fighterId={fighter.id} fighterName={fighter.name} />}

      <SessionRecordingsCard fighterId={params.id} sensor="wrists" />

      <div className="card">
        <h2 className="text-base font-semibold">Available now</h2>
        <ul className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Signal
            live
            title="Wrist acceleration & rotation"
            desc="Each wrist's 3-axis acceleration (±16 g) and rotation rate at 100 Hz, stored with every session on the video's timeline."
          />
          <Signal
            live
            title="Peak force of each punch"
            desc="How hard each counted punch accelerated the wrist (g) — the force the fighter delivered. In the session's per-round breakdown."
          />
        </ul>
      </div>

      {/* Research plans, kept apart so nobody mistakes them for working features. */}
      <details className="card group">
        <summary className="cursor-pointer list-none text-base font-semibold">
          <span className="mr-1 inline-block transition-transform group-open:rotate-90">▸</span>
          Research roadmap — not built yet
        </summary>
        <p className="mt-2 text-sm text-neutral-300">
          What the wrist sensors could add later. None of these gives a result today.
        </p>
        <ul className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Signal
            title="Punch type from rotation"
            desc="The rotation trace could tell straight punches (the forearm turns over) from hooks and uppercuts. Punch types come from the cameras today."
          />
          <Signal
            title="Contact or air"
            desc="A sharp deceleration when the glove lands could tell bag and pad work from shadowboxing."
          />
          <Signal
            title="Pace across a round"
            desc="The time between punches, round by round — how the work rate changes as a round goes on."
          />
          <Signal
            title="Left/right balance"
            desc="Output compared between the hands."
          />
        </ul>
      </details>
    </div>
  );
}

function Signal({ title, desc, live = false }: { title: string; desc: string; live?: boolean }) {
  return (
    <li
      className={`rounded-xl border p-3 ${
        live ? "border-emerald-500/30 bg-emerald-500/5" : "border-dashed border-white/15 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-neutral-100">{title}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
            live ? "bg-emerald-900/60 text-emerald-200" : "bg-neutral-700 text-neutral-200"
          }`}
        >
          {live ? "available" : "not built"}
        </span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-neutral-300">{desc}</p>
    </li>
  );
}
