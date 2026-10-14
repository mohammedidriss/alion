"use client";

/**
 * Live wrist IMUs — the WT901 pair over Bluetooth (configured with
 * scripts/imu_tool.py). The pair belongs to one fighter; it streams into that
 * fighter's sessions, starting and stopping with the cameras.
 *
 * <ImuSensorsPanel> is the fighter IMU tab: names, wrists, owner, live check.
 * The session page's live view is <LiveReader>.
 */

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ImuBleStatus,
  type ImuDevices,
  type ImuHand,
  type ImuUnitStatus,
} from "@/lib/api";

const HANDS: ImuHand[] = ["left", "right"];

/** "409 {"detail":"…"}" → "…" — the API's message, not the transport noise. */
export function imuErrorText(e: unknown): string {
  const text = String(e instanceof Error ? e.message : e);
  const m = text.match(/^\d{3} (.*)$/s);
  if (m) {
    try {
      const body = JSON.parse(m[1]);
      if (typeof body?.detail === "string") return body.detail;
    } catch {
      /* not JSON — fall through */
    }
  }
  return text;
}

function shortAddress(addr: string): string {
  return addr.length > 12 ? `${addr.slice(0, 4)}…${addr.slice(-4)}` : addr;
}

function BatteryBadge({ unit }: { unit: ImuUnitStatus }) {
  if (unit.battery_v == null) return <span className="text-neutral-600">—</span>;
  const pct = unit.battery_pct ?? 0;
  const cls = pct >= 50 ? "text-emerald-300" : pct >= 20 ? "text-amber-300" : "text-red-300";
  return (
    <span className={cls} title={`${unit.battery_v.toFixed(2)} V`}>
      🔋 {pct}%
    </span>
  );
}

function LinkDot({ unit, live }: { unit: ImuUnitStatus | undefined; live: boolean }) {
  const ok = unit?.connected;
  const color = ok ? "bg-emerald-500" : unit?.error ? "bg-red-500" : live ? "bg-amber-500 animate-pulse" : "bg-neutral-600";
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} />;
}

// ---------------------------------------------------------------------------
// Fighter IMU tab
// ---------------------------------------------------------------------------

export function ImuSensorsPanel({
  fighterId,
  fighterName,
}: {
  fighterId: string;
  fighterName: string;
}) {
  const [devices, setDevices] = useState<ImuDevices | null>(null);
  const [check, setCheck] = useState<ImuBleStatus | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [checking, setChecking] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .imuDevices()
      .then(setDevices)
      .catch((e) => setErr(imuErrorText(e)));
  }, []);

  const runCheck = useCallback(async () => {
    setChecking(true);
    setErr(null);
    try {
      setCheck(await api.checkImuDevices());
      setCheckedAt(new Date());
    } catch (e) {
      setErr(imuErrorText(e));
    } finally {
      setChecking(false);
    }
  }, []);

  const assign = useCallback(async () => {
    setAssigning(true);
    setErr(null);
    try {
      setDevices(await api.setImuOwner(fighterId));
    } catch (e) {
      setErr(imuErrorText(e));
    } finally {
      setAssigning(false);
    }
  }, [fighterId]);

  if (!devices) {
    return (
      <div className="card text-sm text-neutral-400">
        {err ? <span className="text-red-300">{err}</span> : "Loading sensors…"}
      </div>
    );
  }

  if (devices.units.length === 0) {
    return (
      <div className="card space-y-2 text-sm text-neutral-300">
        <p className="font-medium text-neutral-100">The wrist sensors aren&apos;t set up on this computer yet</p>
        <p>Ask whoever set up Alion here to pair the two sensors, then reload this page.</p>
        <details className="text-xs text-neutral-400">
          <summary className="cursor-pointer">Technical details</summary>
          <p className="mt-2">Pair the two WT901 units from a terminal:</p>
          <pre className="mt-1 overflow-x-auto rounded bg-black/40 p-2 text-xs text-neutral-300">
            python scripts/imu_tool.py scan{"\n"}python scripts/imu_tool.py assign
          </pre>
        </details>
      </div>
    );
  }

  const ownedHere = devices.owner?.fighter_id === fighterId;
  // The check's verdict, in words: what's connected, what's low, what to do.
  const results = HANDS.map((hand) => ({ hand, unit: devices.units.find((u) => u.hand === hand), live: check?.units[hand] }));
  const down = results.filter((r) => r.unit && !r.live?.connected);
  const low = results.filter((r) => r.live?.connected && r.live.battery_pct != null && r.live.battery_pct < 20);

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Wrist sensors</h2>
          <p className="mt-1 text-sm text-neutral-300">
            One on each wrist: they measure each punch&apos;s force and how fast the forearm turns,
            and record by themselves when the cameras start.
          </p>
        </div>
        <button
          onClick={runCheck}
          disabled={checking}
          className="rounded-xl bg-blue-600 px-3 py-1.5 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
        >
          {checking ? "Checking…" : check ? "Check again" : "Check sensors"}
        </button>
      </div>

      {/* The check's result */}
      {checking ? (
        <div className="rounded-xl border border-white/10 px-3 py-2 text-sm text-neutral-300">
          Connecting to both sensors — a few seconds…
        </div>
      ) : !check ? (
        <div className="rounded-xl border border-white/10 px-3 py-2 text-sm text-neutral-300">
          Not checked yet. Switch both sensors on, then press <b>Check sensors</b> — it takes a few
          seconds and records nothing.
        </div>
      ) : down.length === 0 ? (
        <div className="space-y-1 rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm">
          <p className="font-medium text-emerald-200">
            ✓ Both sensors connected
            {checkedAt && <span className="font-normal text-emerald-300/80"> · checked {checkedAt.toLocaleTimeString()}</span>}
          </p>
          {low.length > 0 ? (
            <p className="text-amber-200">
              Charge the {low.map((r) => `${r.hand} sensor (${r.live?.battery_pct}%)`).join(" and the ")} before a long
              session.
            </p>
          ) : (
            <p className="text-emerald-100/90">Ready — they start recording with the cameras.</p>
          )}
        </div>
      ) : (
        <div className="space-y-1 rounded-xl border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm">
          <p className="font-medium text-red-200">
            ✗ {down.map((r) => `${r.hand} wrist`).join(" and ")} sensor not connected
            {checkedAt && <span className="font-normal text-red-300/80"> · checked {checkedAt.toLocaleTimeString()}</span>}
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-neutral-200">
            <li>Switch it on — its light should blink.</li>
            <li>Bring it within a few metres of this computer.</li>
            <li>Close any other page or app that might be connected to it.</li>
            <li>
              Then press <b>Check again</b>. Without it, sessions still record — just without that wrist.
            </li>
          </ul>
        </div>
      )}

      {/* Owner */}
      <div
        className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-sm ${
          ownedHere ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"
        }`}
      >
        {ownedHere ? (
          <span className="text-emerald-200">
            Worn by <strong>{fighterName}</strong> — the sensors record into this fighter&apos;s sessions.
          </span>
        ) : (
          <>
            <span className="text-amber-200">
              {devices.owner
                ? <>Assigned to <strong>{devices.owner.name}</strong> — they don&apos;t record into this fighter&apos;s sessions.</>
                : "Not assigned to a fighter yet."}
            </span>
            <button
              onClick={assign}
              disabled={assigning}
              className="rounded-lg bg-amber-500 px-2.5 py-1 text-xs font-semibold text-black hover:bg-amber-400 disabled:opacity-50"
            >
              {assigning ? "Assigning…" : `Assign to ${fighterName}`}
            </button>
          </>
        )}
      </div>

      {/* One card per wrist, in plain words */}
      <div className="grid gap-3 sm:grid-cols-2">
        {results.map(({ hand, unit, live }) => (
          <div key={hand} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold capitalize text-neutral-100">{hand} wrist</span>
              {unit && <LinkDot unit={live} live={checking} />}
            </div>
            {!unit ? (
              <div className="mt-1 text-sm text-neutral-300">No sensor set up for this wrist.</div>
            ) : live ? (
              live.connected ? (
                <div className="mt-1 flex flex-wrap gap-x-3 text-sm">
                  <span className="text-emerald-300">Connected</span>
                  <BatteryBadge unit={live} />
                </div>
              ) : (
                <div className="mt-1 text-sm text-red-300">Not connected</div>
              )
            ) : (
              <div className="mt-1 text-sm text-neutral-400">{checking ? "Connecting…" : "Not checked yet"}</div>
            )}
          </div>
        ))}
      </div>

      {err && <p className="text-sm text-red-300">{err}</p>}

      <details className="text-xs text-neutral-400">
        <summary className="cursor-pointer text-neutral-300">Technical details</summary>
        <div className="mt-2 space-y-2">
          <p>WitMotion WT901 · Bluetooth Low Energy · 100 samples a second · ±16 g · rotation in °/s.</p>
          {results.map(({ hand, unit, live }) =>
            unit ? (
              <div key={hand} className="flex flex-wrap gap-x-3 font-mono text-[11px] text-neutral-400">
                <span className="capitalize">{hand}</span>
                <span>{unit.name ?? "WT901"}</span>
                <span title={unit.address}>{shortAddress(unit.address)}</span>
                {live?.connected && (
                  <>
                    <span>{live.hz.toFixed(0)} Hz</span>
                    <span title="Acceleration magnitude at rest should read about 1.00 g">{live.last_g.toFixed(2)} g at rest</span>
                    {live.battery_v != null && <span>{live.battery_v.toFixed(2)} V</span>}
                  </>
                )}
                {live && !live.connected && live.error && <span className="text-red-300">{live.error}</span>}
              </div>
            ) : null,
          )}
          {check?.error && <p className="text-red-300">{check.error}</p>}
        </div>
      </details>
    </div>
  );
}
