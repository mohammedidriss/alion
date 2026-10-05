"use client";

/**
 * JoinQrCard (ADR-010) — the QR code a phone scans to join the session as a
 * camera. No link text: the QR is the join path; the coach just points a phone
 * at it. `compact` is the header version, and it's the *studio* link instead:
 * a phone scans it once and from then on follows every session or take the coach
 * opens (app/camera). Opening a page with this header points the linked phones at
 * that page's capture.
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
    if (compact) return; // the header shows the studio link (StudioQr)
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
  }, [sessionId, takeId, compact]);

  if (compact) return <StudioQr sessionId={sessionId} takeId={takeId} />;

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

/** A phone-reachable URL for `path`: the coach's own origin, or the LAN IP when the
 *  coach opened the dashboard on localhost (a phone can't reach that). */
function phoneUrl(path: string, lanIp: string | null): string {
  const loc = window.location;
  const isLocal = loc.hostname === "localhost" || loc.hostname === "127.0.0.1";
  if (isLocal && lanIp) return `${loc.protocol}//${lanIp}${loc.port ? `:${loc.port}` : ""}${path}`;
  return `${loc.origin}${path}`;
}

/** The studio QR: scan once per phone; linked phones follow whatever capture is open.
 *  Mounting it makes this page's session / take the studio's active capture. */
function StudioQr({ sessionId, takeId }: { sessionId?: string; takeId?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [phones, setPhones] = useState<{ phone_id: string; label: string }[]>([]);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const kind = takeId ? "take" : "session";
    const id = takeId ?? sessionId;
    const first = id ? api.setStudioActive(kind, id) : api.studio();
    first
      .then((st) => {
        if (!alive) return;
        setUrl(phoneUrl(st.join_path, st.lan_ip));
        setPhones(st.phones);
      })
      .catch(() => alive && setErr(true));
    const poll = setInterval(() => {
      api
        .studio()
        .then((st) => alive && setPhones(st.phones))
        .catch(() => {});
    }, 3000);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, [sessionId, takeId]);

  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-neutral-950/60 p-2 pr-4">
      {url ? (
        <div className="shrink-0 overflow-hidden rounded-lg bg-white">
          <QRCodeSVG value={url} size={QR_PX} marginSize={4} />
        </div>
      ) : (
        <div
          className="flex shrink-0 items-center justify-center rounded-lg border border-dashed border-white/10 text-xs text-neutral-500"
          style={{ width: QR_PX, height: QR_PX }}
        >
          {err ? "Could not build the link." : "…"}
        </div>
      )}
      <div className="max-w-[12rem] leading-tight">
        <div className="text-sm font-semibold text-neutral-200">Link a phone camera</div>
        <div className="mt-1 text-xs text-neutral-500">
          Scan once per phone — it then joins every session and take you open.
        </div>
        <div className="mt-2 space-y-0.5">
          {phones.length === 0 ? (
            <div className="text-xs text-neutral-600">No phones linked yet</div>
          ) : (
            phones.map((p) => (
              <div key={p.phone_id} className="flex items-center gap-1.5 text-xs text-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                {p.label}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
