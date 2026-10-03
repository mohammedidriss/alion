"use client";

import { useEffect, useState } from "react";
import { ImuSensorsPanel } from "@/components/ImuSensors";
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

      <div className="card">
        <h2 className="text-base font-semibold">Signals</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Raw 100 Hz streams are recorded now. The derived signals come with the IMU
          punch detector.
        </p>
        <ul className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Signal
            live
            title="Wrist acceleration & gyro"
            desc="Raw 3-axis acceleration (±16 g) and rotation rate for each wrist, stored per session."
          />
          <Signal
            title="Per-punch acceleration peak"
            desc="Direct g-force at the wrist, an independent ground truth for the CV-derived velocity."
          />
          <Signal
            title="Punch type from rotation"
            desc="The gyro trace separates straight punches (pronation) from hooks and uppercuts."
          />
          <Signal
            title="Impact detection"
            desc="A sharp deceleration spike when the glove lands. Separates contact from shadowboxing."
          />
          <Signal
            title="Cadence & fatigue"
            desc="Inter-punch intervals per round. Intervals lengthen as the fighter tires."
          />
          <Signal
            title="Left/right asymmetry"
            desc="Compare output between hands to flag dominance or compensation patterns."
          />
        </ul>
      </div>
    </div>
  );
}

function Signal({ title, desc, live = false }: { title: string; desc: string; live?: boolean }) {
  return (
    <li
      className={`rounded-xl border p-3 ${
        live ? "border-emerald-500/30 bg-emerald-500/5" : "border-dashed border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-neutral-200">{title}</span>
        <span
          className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium ${
            live ? "bg-emerald-900/60 text-emerald-300" : "bg-neutral-800 text-neutral-400"
          }`}
        >
          {live ? "recording" : "planned"}
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-500">{desc}</p>
    </li>
  );
}
