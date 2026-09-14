"use client";

/**
 * Multi-camera device panel (ADR-010) — the master/coach view. Shows a live grid
 * of every connected camera (≈1 fps preview frames each phone posts), the join QR,
 * one synchronized Start/Stop, and playback of the recorded per-device clips.
 */

import { useCallback, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api, type MulticamDevice } from "@/lib/api";

export function MulticamPanel({ sessionId }: { sessionId: string }) {
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<MulticamDevice[]>([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .multicamJoinInfo(sessionId)
      .then((ji) => {
        setToken(ji.join_token);
        const loc = window.location;
        const isLocal = loc.hostname === "localhost" || loc.hostname === "127.0.0.1";
        // Use whatever origin the coach is on — a tunnel URL, or the LAN IP. Only
        // fall back to the server's LAN IP when the coach opened it via localhost.
        if (isLocal && ji.lan_ip) {
          const port = loc.port ? `:${loc.port}` : "";
          setJoinUrl(`${loc.protocol}//${ji.lan_ip}${port}${ji.join_path}`);
        } else {
          setJoinUrl(`${loc.origin}${ji.join_path}`);
        }
      })
      .catch(() => setMsg("Could not fetch the join link."));
  }, [sessionId]);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .multicamDevices(sessionId)
        .then((d) => alive && setDevices(d))
        .catch(() => {});
    const id = setInterval(poll, 1500);
    poll();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId]);

  // Refresh the live-grid frames ~1×/s.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.multicamStart(sessionId);
      setMsg(`Recording ${r.devices} camera(s) together…`);
    } catch {
      setMsg("Connect at least one camera first.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const stop = useCallback(async () => {
    await api.multicamStop(sessionId).catch(() => {});
    setMsg("Stopped — clips uploading. They appear under “Camera recordings” below.");
  }, [sessionId]);

  const copy = useCallback(() => {
    if (!joinUrl) return;
    navigator.clipboard?.writeText(joinUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [joinUrl]);

  const cams = devices.filter((d) => d.role === "camera");
  const maxPunches = cams.reduce((m, c) => Math.max(m, c.punches), 0);

  return (
    <div className="rounded-2xl border border-white/10 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Cameras</h3>
        <span className="text-xs text-neutral-500">
          {cams.length} connected
          {maxPunches > 0 && <span className="text-emerald-400"> · ~{maxPunches} punches</span>}
        </span>
      </div>

      {/* Live grid — one tile per camera, refreshed ~1×/s */}
      {cams.length > 0 && token && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {cams.map((d) => (
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
                <span>📷 {d.label}</span>
                <span className="flex items-center gap-2">
                  {d.punches > 0 && (
                    <span className="font-semibold text-emerald-400">{d.punches}👊</span>
                  )}
                  <StatusDot status={d.status} />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Join QR */}
      <div className="space-y-2">
        <p className="text-xs text-neutral-400">Scan on each phone (same Wi-Fi) to add a camera:</p>
        {joinUrl ? (
          <div className="flex items-center gap-3">
            <div className="shrink-0 rounded-lg bg-white p-2">
              <QRCodeSVG value={joinUrl} size={104} />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <code className="block truncate rounded-lg bg-black/40 px-2 py-1.5 text-xs text-neutral-300">
                {joinUrl}
              </code>
              <button
                onClick={copy}
                className="rounded-lg border border-white/10 px-3 py-1.5 text-xs hover:bg-white/5"
              >
                {copied ? "Copied" : "Copy link"}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-neutral-500">…</p>
        )}
      </div>

      {cams.length === 0 && (
        <p className="text-xs text-neutral-500">No cameras yet — scan the code on a phone.</p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          onClick={start}
          disabled={busy || cams.length === 0}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          Start all cameras
        </button>
        <button
          onClick={stop}
          className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/5"
        >
          Stop
        </button>
      </div>
      {msg && <p className="text-xs text-neutral-400">{msg}</p>}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "recording" ? "bg-red-500" : status === "ready" ? "bg-emerald-500" : "bg-neutral-500";
  return (
    <span className="inline-flex items-center gap-1 text-neutral-300">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {status}
    </span>
  );
}
