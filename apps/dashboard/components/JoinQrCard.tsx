"use client";

/**
 * JoinQrCard (ADR-010) — a small panel under the round configuration that shows
 * only the QR code a phone scans to join the session as a camera. No link text:
 * the QR is the join path; the coach just points a phone at it.
 */

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";

export function JoinQrCard({ sessionId }: { sessionId: string }) {
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api
      .multicamJoinInfo(sessionId)
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
  }, [sessionId]);

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
