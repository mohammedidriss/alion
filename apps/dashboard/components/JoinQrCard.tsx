"use client";

/**
 * JoinQrCard (ADR-010) — the QR code a phone scans to join the session as a
 * camera. No link text: the QR is the join path; the coach just points a phone
 * at it. `compact` is the header version: the QR beside a short label.
 *
 * Every code carries a 4-module white border (the QR "quiet zone"): scanners
 * can't find a code without one, and the CSS padding alone was only ~1 module.
 */

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";

// Big enough for a phone to read straight off a laptop screen (~3.4 px per module
// for a join link): a 52 px code only decoded at Retina density.
const QR_PX = 168;

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
          <div className="rounded-lg bg-white">
            <QRCodeSVG value={joinUrl} size={180} marginSize={4} />
          </div>
        </div>
      ) : (
        <p className="text-xs text-neutral-500">{err ? "Could not build the join link." : "…"}</p>
      )}
    </div>
  );
}

function CompactQr({ joinUrl, err }: { joinUrl: string | null; err: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-neutral-950/60 p-2 pr-4">
      {joinUrl ? (
        <div className="shrink-0 overflow-hidden rounded-lg bg-white">
          <QRCodeSVG value={joinUrl} size={QR_PX} marginSize={4} />
        </div>
      ) : (
        <div
          className="flex shrink-0 items-center justify-center rounded-lg border border-dashed border-white/10 text-xs text-neutral-500"
          style={{ width: QR_PX, height: QR_PX }}
        >
          {err ? "Could not build the join link." : "…"}
        </div>
      )}
      <div className="leading-tight">
        <div className="text-sm font-semibold text-neutral-200">Add a phone camera</div>
        <div className="mt-1 text-xs text-neutral-500">Scan with the phone&apos;s camera</div>
        <div className="text-xs text-neutral-500">Same Wi-Fi as this laptop</div>
      </div>
    </div>
  );
}
