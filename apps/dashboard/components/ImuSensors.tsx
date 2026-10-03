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
      <div className="card text-sm text-neutral-400">
        <p className="font-medium text-neutral-200">No IMU sensors set up on this Mac</p>
        <p className="mt-2">
          Pair the two WT901 units from a terminal, then reload this page:
        </p>
        <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-2 text-xs text-neutral-300">
          python scripts/imu_tool.py scan{"\n"}python scripts/imu_tool.py assign
        </pre>
      </div>
    );
  }

  const ownedHere = devices.owner?.fighter_id === fighterId;

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Wrist sensors</h2>
          <p className="mt-1 text-xs text-neutral-500">
            WitMotion WT901 · Bluetooth · 100 Hz · ±16 g
          </p>
        </div>
        <button
          onClick={runCheck}
          disabled={checking}
          className="rounded-xl bg-blue-600 px-3 py-1.5 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
        >
          {checking ? "Connecting…" : "Check sensors"}
        </button>
      </div>

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

      {/* One row per wrist */}
      <div className="grid gap-3 sm:grid-cols-2">
        {HANDS.map((hand) => {
          const unit = devices.units.find((u) => u.hand === hand);
          const live = check?.units[hand];
          return (
            <div key={hand} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-neutral-400">
                  {hand} wrist
                </span>
                {unit && <LinkDot unit={live} live={checking} />}
              </div>
              {unit ? (
                <>
                  <div className="mt-1 text-lg font-semibold">{unit.name ?? "WT901"}</div>
                  <div className="font-mono text-[11px] text-neutral-500" title={unit.address}>
                    {shortAddress(unit.address)}
                  </div>
                  {live ? (
                    live.connected ? (
                      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-300">
                        <span className="text-emerald-300">connected</span>
                        <span>{live.hz.toFixed(0)} Hz</span>
                        <BatteryBadge unit={live} />
                        <span title="Acceleration magnitude at rest should read ~1.00 g">
                          {live.last_g.toFixed(2)} g
                        </span>
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-red-300">{live.error ?? "not connected"}</div>
                    )
                  ) : (
                    <div className="mt-2 text-xs text-neutral-500">
                      {checking ? "connecting…" : "Press Check sensors to test the link."}
                    </div>
                  )}
                </>
              ) : (
                <div className="mt-2 text-xs text-neutral-500">
                  No unit assigned — run <code>imu_tool.py assign</code>.
                </div>
              )}
            </div>
          );
        })}
      </div>

      {check?.error && <p className="text-xs text-red-300">{check.error}</p>}
      {err && <p className="text-xs text-red-300">{err}</p>}
      <p className="text-[11px] text-neutral-500">
        Check takes a few seconds and stores nothing. Switch both sensors on first. During a
        session they start and stop with the cameras.
      </p>
    </div>
  );
}
