"use client";

/**
 * JoinQrCard (ADR-010) — the QR code a phone scans to join the session as a
 * camera. No link text: the QR is the join path; the coach just points a phone
 * at it. `compact` is the slim header version (session page): a small QR that
 * enlarges on click, since a tiny on-screen code is hard for a phone to read.
 */

import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";

export function JoinQrCard({
  sessionId,
  takeId,
  compact = false,
}: {
  sessionId?: string;
  takeId?: string; // a dataset take instead of a session (ADR-013)
  compact?: boolean;
}) {
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api
      .multicamJoinInfo(takeId ? { kind: "take", id: takeId } : (sessionId ?? ""))
      .then((ji) => {
        const loc = window.location;
        const isLocal = loc.hostname === "localhost" || loc.hostname === "127.0.0.1";
        // Use whatever origin the coach is on; only fall back to the server's LAN
        // IP when opened via localhost (a phone can't reach the coach's localhost).
        if (isLocal && ji.lan_ip) {
          const port = loc.port ? `:${loc.port}` : "";
          setJoinUrl(`${loc.protocol}//${ji.lan_ip}${port}${ji.join_path}`);
        } else {
          setJoinUrl(`${loc.origin}${ji.join_path}`);
        }
      })
      .catch(() => setErr(true));
  }, [sessionId, takeId]);

  if (compact) return <CompactQr joinUrl={joinUrl} err={err} />;

  return (
    <div className="rounded-2xl border border-white/10 p-4 space-y-3">
      <h3 className="text-sm font-semibold">Add a phone camera</h3>
      <p className="text-xs text-neutral-400">Scan on each phone (same Wi-Fi).</p>
      {joinUrl ? (
        <div className="flex justify-center">
          <div className="rounded-lg bg-white p-2">
            <QRCodeSVG value={joinUrl} size={148} />
          </div>
        </div>
      ) : (
        <p className="text-xs text-neutral-500">{err ? "Could not build the join link." : "…"}</p>
      )}
    </div>
  );
}

function CompactQr({ joinUrl, err }: { joinUrl: string | null; err: boolean }) {
  const [big, setBig] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close the enlarged code on a click elsewhere or Escape.
  useEffect(() => {
    if (!big) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setBig(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setBig(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [big]);

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-neutral-950/60 py-1 pl-1 pr-3">
        {joinUrl ? (
          <button
            onClick={() => setBig((b) => !b)}
            className="rounded-md bg-white p-0.5 transition-transform hover:scale-105"
            title="Click to enlarge"
            aria-label="Enlarge the camera join QR code"
          >
            <QRCodeSVG value={joinUrl} size={52} />
          </button>
        ) : (
          <div className="flex h-[56px] w-[56px] items-center justify-center rounded-md border border-dashed border-white/10 text-[10px] text-neutral-500">
            {err ? "no link" : "…"}
          </div>
        )}
        <div className="leading-tight">
          <div className="text-xs font-semibold text-neutral-200">Add a phone camera</div>
          <div className="mt-0.5 text-[11px] text-neutral-500">Scan · same Wi-Fi</div>
          <div className="text-[10px] text-neutral-600">click to enlarge</div>
        </div>
      </div>
      {big && joinUrl && (
        <div className="absolute left-1/2 top-full z-30 mt-2 -translate-x-1/2 rounded-2xl border border-white/10 bg-neutral-900 p-3 shadow-2xl">
          <div className="rounded-xl bg-white p-3">
            <QRCodeSVG value={joinUrl} size={220} />
          </div>
          <p className="mt-2 text-center text-[11px] text-neutral-400">Click anywhere to close</p>
        </div>
      )}
    </div>
  );
}
