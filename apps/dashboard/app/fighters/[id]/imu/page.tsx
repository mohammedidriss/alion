"use client";

export default function ImuTab() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">IMU</h1>
        <p className="text-sm text-neutral-400">
          Wrist-worn inertial sensors — currently inactive.
        </p>
      </header>

      <div className="card border-amber-500/20 bg-amber-500/5">
        <p className="font-medium text-amber-200">No IMU stream wired up</p>
        <p className="mt-2 text-sm text-amber-100/70">
          IMU integration is parked pending a hardware decision. The Hykso /
          Corner / Everlast PIQ family of wrist trackers were considered but
          all are out of stock or shipped on extended lead times. We&apos;ll
          revisit once Phase 2 HRV (Polar H10) is fully live.
        </p>
      </div>

      <div className="card">
        <h2 className="text-base font-semibold">Planned signals</h2>
        <p className="mt-1 text-xs text-neutral-500">
          What this tab will surface once an IMU is integrated. Listed so the
          schema and UI scaffolding is visible up-front rather than invented
          when the first device arrives.
        </p>
        <ul className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Planned
            title="Per-punch acceleration peak"
            desc="Direct g-force measurement at the wrist — independent ground truth for the CV-derived velocity."
          />
          <Planned
            title="Hand orientation trace"
            desc="Quaternion / Euler stream during the punch — distinguishes pronation (cross) from rotation (hook)."
          />
          <Planned
            title="IMU velocity"
            desc="Integrated acceleration → fist velocity (m/s). Cross-validate the CV detector and reduce false positives."
          />
          <Planned
            title="Impact detection"
            desc="Sharp deceleration spike when the glove contacts a target. Confirms intent vs shadowboxing."
          />
          <Planned
            title="Cadence histogram"
            desc="Inter-punch interval distribution per round — reveals fatigue (intervals lengthen as the round wears on)."
          />
          <Planned
            title="Left/right asymmetry"
            desc="Compare mean output between hands. Flag dominance or compensation patterns."
          />
        </ul>
      </div>

      <div className="card text-xs text-neutral-500">
        <p className="font-medium text-neutral-300">Architecture note</p>
        <p className="mt-2">
          IMU will land as <code className="rounded bg-black/30 px-1">capture/imu/</code>{" "}
          — a sibling of <code className="rounded bg-black/30 px-1">capture/cv/</code>
          {" "}and <code className="rounded bg-black/30 px-1">capture/hrv/</code>. Same
          contracts pattern, same /v3 API surface, no rewrites of existing
          code (per ADR 005).
        </p>
      </div>
    </div>
  );
}

function Planned({ title, desc }: { title: string; desc: string }) {
  return (
    <li className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-3">
      <div className="text-sm font-medium text-neutral-200">{title}</div>
      <p className="mt-1 text-xs text-neutral-500">{desc}</p>
    </li>
  );
}
