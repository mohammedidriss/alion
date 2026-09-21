"use client";

/**
 * Unified bout capture + live scorecard (ADR-011 step 5). One page for a two-fighter
 * fight: both corners side by side, one shared round timer, one Start fight / Pause /
 * Stop driving both corners, a live punch count per fighter, a per-fighter log
 * (punches, knockdowns, control time), a live win-probability estimate, and a
 * knockdown highlight.
 *
 * Punches come from CV (per-corner session). Knockdowns and control are *logged*
 * events — a ref/coach taps them — because reliable automatic knockdown detection
 * needs the multi-cam + IMU attribution that isn't built yet. Win probability is a
 * transparent heuristic over the live stats, not a trained model. Scorecard state is
 * client-side for now (not yet persisted to the bout).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CameraNode } from "@/components/CameraNode";
import { JoinQrCard } from "@/components/JoinQrCard";
import { RoundTimer } from "@/components/SessionRounds";
import { api, type Bout, type MulticamDevice, type Session } from "@/lib/api";

type Corner = "red" | "blue";

// Win-probability weights: a knockdown ≈ a dominant round of punches (boxing scores
// a knockdown 10-8), control adds per minute. Tunable; documented so it's honest.
const W_PUNCH = 1;
const W_KNOCKDOWN = 12;
const W_CONTROL_PER_MIN = 3;

function fmtClock(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function BoutCapture({
  bout,
  red,
  blue,
  redName,
  blueName,
}: {
  bout: Bout;
  red: Session;
  blue: Session;
  redName: string;
  blueName: string;
}) {
  const [redToken, setRedToken] = useState<string | null>(null);
  const [blueToken, setBlueToken] = useState<string | null>(null);
  const [redDevices, setRedDevices] = useState<MulticamDevice[]>([]);
  const [blueDevices, setBlueDevices] = useState<MulticamDevice[]>([]);
  const [laptopCorner, setLaptopCorner] = useState<Corner | null>("red");
  const [laptopDeviceId, setLaptopDeviceId] = useState<string | null>(null);
  const [fighting, setFighting] = useState(false);
  const [paused, setPaused] = useState(false);
  const [captureStartMs, setCaptureStartMs] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const pausedAccumRef = useRef(0);
  const pauseStartRef = useRef<number | null>(null);

  // Scorecard (logged): knockdowns, control seconds, who is controlling now.
  const [redKD, setRedKD] = useState(0);
  const [blueKD, setBlueKD] = useState(0);
  const [redControl, setRedControl] = useState(0);
  const [blueControl, setBlueControl] = useState(0);
  const [controlling, setControlling] = useState<Corner | null>(null);
  const [kdFlash, setKdFlash] = useState<{ corner: Corner; name: string } | null>(null);

  useEffect(() => {
    api.multicamJoinInfo(red.id).then((j) => setRedToken(j.join_token)).catch(() => {});
    api.multicamJoinInfo(blue.id).then((j) => setBlueToken(j.join_token)).catch(() => {});
  }, [red.id, blue.id]);

  useEffect(() => {
    let alive = true;
    const poll = () => {
      api.multicamDevices(red.id).then((d) => alive && setRedDevices(d)).catch(() => {});
      api.multicamDevices(blue.id).then((d) => alive && setBlueDevices(d)).catch(() => {});
    };
    const id = setInterval(poll, 1500);
    poll();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [red.id, blue.id]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Accumulate control time for whoever is marked controlling, while the fight runs.
  useEffect(() => {
    if (!fighting || paused || !controlling) return;
    const id = setInterval(() => {
      if (controlling === "red") setRedControl((c) => c + 1);
      else setBlueControl((c) => c + 1);
    }, 1000);
    return () => clearInterval(id);
  }, [fighting, paused, controlling]);

  const redCams = redDevices.filter((d) => d.role === "camera");
  const blueCams = blueDevices.filter((d) => d.role === "camera");
  const redCount = redCams.reduce((m, c) => Math.max(m, c.punches), 0);
  const blueCount = blueCams.reduce((m, c) => Math.max(m, c.punches), 0);
  const canStart = redCams.length > 0 || blueCams.length > 0 || laptopCorner !== null;

  // Live win probability — Laplace-smoothed share of a weighted score (starts 50/50).
  const scoreRed =
    W_PUNCH * redCount + W_KNOCKDOWN * redKD + W_CONTROL_PER_MIN * (redControl / 60);
  const scoreBlue =
    W_PUNCH * blueCount + W_KNOCKDOWN * blueKD + W_CONTROL_PER_MIN * (blueControl / 60);
  const pRed = (scoreRed + 1) / (scoreRed + scoreBlue + 2);
  const redPct = Math.round(pRed * 100);

  const activeMs = captureStartMs
    ? Math.max(
        0,
        Date.now() -
          captureStartMs -
          pausedAccumRef.current -
          (pauseStartRef.current != null ? Date.now() - pauseStartRef.current : 0),
      )
    : 0;

  const logKnockdown = useCallback(
    (corner: Corner) => {
      const name = corner === "red" ? redName : blueName;
      if (corner === "red") setRedKD((k) => k + 1);
      else setBlueKD((k) => k + 1);
      setKdFlash({ corner, name });
      window.setTimeout(() => setKdFlash(null), 4500);
    },
    [redName, blueName],
  );

  const toggleControl = useCallback((corner: Corner) => {
    setControlling((cur) => (cur === corner ? null : corner));
  }, []);

  const startFight = useCallback(async () => {
    setMsg(null);
    const r = await api.multicamStart(red.id).catch(() => null);
    const b = await api.multicamStart(blue.id).catch(() => null);
    if (!r && !b) {
      setMsg("Enable a camera on at least one corner first.");
      return;
    }
    pausedAccumRef.current = 0;
    pauseStartRef.current = null;
    setPaused(false);
    setRedKD(0);
    setBlueKD(0);
    setRedControl(0);
    setBlueControl(0);
    setControlling(null);
    setCaptureStartMs(Date.now());
    setFighting(true);
    setMsg("Fight on — recording both corners.");
  }, [red.id, blue.id]);

  const pauseFight = useCallback(async () => {
    await Promise.all([
      api.multicamPause(red.id).catch(() => {}),
      api.multicamPause(blue.id).catch(() => {}),
    ]);
    pauseStartRef.current = Date.now();
    setPaused(true);
  }, [red.id, blue.id]);

  const resumeFight = useCallback(async () => {
    await Promise.all([
      api.multicamResume(red.id).catch(() => {}),
      api.multicamResume(blue.id).catch(() => {}),
    ]);
    if (pauseStartRef.current != null) {
      pausedAccumRef.current += Date.now() - pauseStartRef.current;
      pauseStartRef.current = null;
    }
    setPaused(false);
  }, [red.id, blue.id]);

  const stopFight = useCallback(async () => {
    await Promise.all([
      api.multicamStop(red.id).catch(() => {}),
      api.multicamStop(blue.id).catch(() => {}),
    ]);
    setCaptureStartMs(null);
    setFighting(false);
    setPaused(false);
    setControlling(null);
    pauseStartRef.current = null;
    pausedAccumRef.current = 0;
    setMsg("Fight ended — clips saved to each fighter's session.");
  }, [red.id, blue.id]);

  const timerSession: Session = {
    ...red,
    round_count: bout.round_count,
    round_duration_s: bout.round_duration_s,
    rest_duration_s: bout.rest_duration_s,
  };

  return (
    <div className="space-y-4">
      {/* Knockdown highlight */}
      {kdFlash && (
        <div
          className={`animate-pulse rounded-2xl border px-4 py-3 text-center text-lg font-bold ${
            kdFlash.corner === "red"
              ? "border-red-500 bg-red-600/30 text-red-100"
              : "border-sky-500 bg-sky-600/30 text-sky-100"
          }`}
        >
          🥊 KNOCKDOWN — {kdFlash.name} scores!
        </div>
      )}

      {/* Scoreboard + win probability */}
      <div className="space-y-3 rounded-2xl border border-white/10 p-4">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <Score corner="red" name={redName} count={redCount} />
          <div className="text-xs font-semibold uppercase text-neutral-500">vs</div>
          <Score corner="blue" name={blueName} count={blueCount} align="right" />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs font-medium">
            <span className="text-red-300">{redPct}%</span>
            <span className="text-neutral-500">win probability (live estimate)</span>
            <span className="text-sky-300">{100 - redPct}%</span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-neutral-800">
            <div className="bg-red-500 transition-all" style={{ width: `${redPct}%` }} />
            <div className="bg-sky-500 transition-all" style={{ width: `${100 - redPct}%` }} />
          </div>
        </div>
      </div>

      {/* One control for the whole fight */}
      <div className="flex flex-wrap items-center gap-2">
        {!fighting ? (
          <button
            onClick={startFight}
            disabled={!canStart}
            className="rounded-xl bg-emerald-500 px-5 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
          >
            ▶ Start fight
          </button>
        ) : (
          <>
            {paused ? (
              <button
                onClick={resumeFight}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400"
              >
                ▶ Resume
              </button>
            ) : (
              <button
                onClick={pauseFight}
                className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-400"
              >
                ❚❚ Pause
              </button>
            )}
            <button
              onClick={stopFight}
              className="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500"
            >
              ■ Stop &amp; save
            </button>
          </>
        )}
        <div className="ml-auto flex items-center gap-1 text-xs text-neutral-400">
          <span>Laptop camera:</span>
          {(["red", "blue"] as Corner[]).map((c) => (
            <button
              key={c}
              onClick={() => {
                setLaptopCorner((cur) => (cur === c ? null : c));
                setLaptopDeviceId(null);
              }}
              className={`rounded-lg px-2 py-1 capitalize ${
                laptopCorner === c
                  ? c === "red"
                    ? "bg-red-600 text-white"
                    : "bg-sky-600 text-white"
                  : "border border-white/10 text-neutral-300 hover:bg-white/5"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>
      {msg && <p className="text-xs text-neutral-400">{msg}</p>}

      {fighting && <RoundTimer session={timerSession} durationMs={activeMs} isPaused={paused} />}

      {/* Two corners: camera + per-fighter log */}
      <div className="grid gap-4 lg:grid-cols-2">
        <CornerPanel
          corner="red"
          name={redName}
          count={redCount}
          knockdowns={redKD}
          controlSec={redControl}
          controlling={controlling === "red"}
          onKnockdown={() => logKnockdown("red")}
          onToggleControl={() => toggleControl("red")}
          sessionId={red.id}
          token={redToken}
          cameras={redCams}
          laptopHere={laptopCorner === "red"}
          laptopDeviceId={laptopDeviceId}
          onLaptopDeviceId={setLaptopDeviceId}
          tick={tick}
        />
        <CornerPanel
          corner="blue"
          name={blueName}
          count={blueCount}
          knockdowns={blueKD}
          controlSec={blueControl}
          controlling={controlling === "blue"}
          onKnockdown={() => logKnockdown("blue")}
          onToggleControl={() => toggleControl("blue")}
          sessionId={blue.id}
          token={blueToken}
          cameras={blueCams}
          laptopHere={laptopCorner === "blue"}
          laptopDeviceId={laptopDeviceId}
          onLaptopDeviceId={setLaptopDeviceId}
          tick={tick}
        />
      </div>
    </div>
  );
}

function Score({
  corner,
  name,
  count,
  align = "left",
}: {
  corner: Corner;
  name: string;
  count: number;
  align?: "left" | "right";
}) {
  const color = corner === "red" ? "text-red-400" : "text-sky-400";
  return (
    <div className={align === "right" ? "text-right" : "text-left"}>
      <div className={`text-xs font-semibold uppercase ${color}`}>{corner} corner</div>
      <div className="truncate text-lg font-semibold">{name}</div>
      <div className="mt-1">
        <span className="text-4xl font-bold tabular-nums text-emerald-400">{count}</span>
        <span className="ml-1 text-sm text-neutral-400">punches</span>
      </div>
    </div>
  );
}

function CornerPanel({
  corner,
  name,
  count,
  knockdowns,
  controlSec,
  controlling,
  onKnockdown,
  onToggleControl,
  sessionId,
  token,
  cameras,
  laptopHere,
  laptopDeviceId,
  onLaptopDeviceId,
  tick,
}: {
  corner: Corner;
  name: string;
  count: number;
  knockdowns: number;
  controlSec: number;
  controlling: boolean;
  onKnockdown: () => void;
  onToggleControl: () => void;
  sessionId: string;
  token: string | null;
  cameras: MulticamDevice[];
  laptopHere: boolean;
  laptopDeviceId: string | null;
  onLaptopDeviceId: (id: string) => void;
  tick: number;
}) {
  const tint = corner === "red" ? "border-red-500/40" : "border-sky-500/40";
  const label = corner === "red" ? "text-red-300" : "text-sky-300";
  const phones = cameras.filter((d) => d.device_id !== laptopDeviceId);

  return (
    <div className={`space-y-3 rounded-2xl border ${tint} p-4`}>
      <div className="flex items-center justify-between">
        <span className={`text-sm font-semibold uppercase ${label}`}>
          {corner} · {name}
        </span>
        <span className="text-sm text-neutral-300">
          <b className="text-lg text-emerald-400">{count}</b> 👊
        </span>
      </div>

      {laptopHere && token && (
        <CameraNode
          sessionId={sessionId}
          token={token}
          defaultLabel={corner}
          tile
          onDeviceId={onLaptopDeviceId}
        />
      )}

      {phones.length > 0 && token && (
        <div className="grid grid-cols-2 gap-2">
          {phones.map((d) => (
            <div
              key={d.device_id}
              className="relative aspect-video overflow-hidden rounded-xl border border-white/10 bg-black"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${api.multicamFrameUrl(sessionId, token, d.device_id)}&t=${tick}`}
                alt={d.label}
                className="h-full w-full object-cover"
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
                }}
                onLoad={(e) => {
                  (e.currentTarget as HTMLImageElement).style.visibility = "visible";
                }}
              />
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/60 px-2 py-1 text-[11px]">
                <span className="truncate">📷 {d.label}</span>
                {d.punches > 0 && <span className="font-semibold text-emerald-400">{d.punches}👊</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {!laptopHere && phones.length === 0 && (
        <p className="text-xs text-neutral-500">
          No camera on this corner — set the laptop to {corner}, or scan the QR below on a phone.
        </p>
      )}

      {/* Per-fighter log / scorecard */}
      <div className="grid grid-cols-3 gap-2 rounded-xl bg-black/30 p-2 text-center">
        <Stat label="Punches" value={count} />
        <Stat label="Knockdowns" value={knockdowns} tone={knockdowns > 0 ? "red" : undefined} />
        <Stat label="Control" value={fmtClock(controlSec)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onKnockdown}
          className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/20"
        >
          🥊 Log knockdown
        </button>
        <button
          onClick={onToggleControl}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            controlling
              ? "bg-amber-500 text-black"
              : "border border-white/10 text-neutral-300 hover:bg-white/5"
          }`}
        >
          {controlling ? "● Controlling" : "Mark control"}
        </button>
      </div>

      {token && (
        <details className="text-xs text-neutral-400">
          <summary className="cursor-pointer select-none">➕ Add a phone camera</summary>
          <div className="mt-2">
            <JoinQrCard sessionId={sessionId} />
          </div>
        </details>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "red";
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div
        className={`text-lg font-semibold tabular-nums ${tone === "red" ? "text-red-400" : "text-neutral-100"}`}
      >
        {value}
      </div>
    </div>
  );
}
