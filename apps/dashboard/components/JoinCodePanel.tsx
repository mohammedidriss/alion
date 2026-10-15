"use client";

/**
 * The gym's join code (ADR-055): fighters ask to join with it — by the link, the QR
 * code, or typing the code on their profile page — and the gym approves. A new
 * code retires the old one; turning it off retires both.
 */

import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export function JoinCodePanel({ gymId }: { gymId: string }) {
  const [code, setCode] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);

  const load = useCallback(() => {
    api
      .gymJoinCode(gymId)
      .then((r) => setCode(r.join_code))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [gymId]);
  useEffect(() => load(), [load]);

  const run = async (fn: () => Promise<{ join_code: string | null }>) => {
    setErr(null);
    try {
      setCode((await fn()).join_code);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const link = code ? `${origin}/join/${code}` : "";
  return (
    <div className="card space-y-3">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-neutral-300">Join code</h3>
        <p className="text-xs text-neutral-500">
          Fighters ask to join with it; you approve each request below, on trial or straight in.
        </p>
      </div>
      {code ? (
        <div className="flex flex-wrap items-center gap-4">
          <div className="rounded-lg bg-white p-2">
            <QRCodeSVG value={link} size={112} />
          </div>
          <div className="space-y-1 text-sm">
            <div className="font-mono text-2xl tracking-widest text-neutral-100 select-all">{code}</div>
            <div className="break-all text-xs text-neutral-400 select-all">{link}</div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => {
                  if (confirm("Make a new code? The current one stops working.")) void run(() => api.newGymJoinCode(gymId));
                }}
                className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/5"
              >
                New code
              </button>
              <button
                onClick={() => void run(() => api.stopGymJoinCode(gymId))}
                className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-neutral-400 hover:bg-white/5"
              >
                Turn off
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          onClick={() => void run(() => api.newGymJoinCode(gymId))}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400"
        >
          Make a join code
        </button>
      )}
      {err && <p className="text-sm text-red-300">{err}</p>}
    </div>
  );
}
