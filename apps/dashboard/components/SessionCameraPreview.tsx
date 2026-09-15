"use client";

/**
 * Session-list camera preview. Multi-camera sessions store per-device clips (not a
 * single `video_path`), so the list can't show them with a plain <video src> — the
 * clip endpoint needs an auth header and serves the whole file. This shows a light
 * "Preview" affordance for any session that has clips (a cheap metadata check) and
 * only downloads the first camera's clip when the coach clicks it — so recordings
 * are watchable straight from the list without opening the session, and without
 * pulling every clip on page load.
 *
 * Renders nothing for sessions with no multi-camera clips.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function SessionCameraPreview({ sessionId }: { sessionId: string }) {
  const [count, setCount] = useState(0);
  const [firstDevice, setFirstDevice] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .multicamClips(sessionId)
      .then((clips) => {
        if (!alive) return;
        setCount(clips.length);
        setFirstDevice(clips[0]?.device_id ?? null);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [sessionId]);

  // Revoke the blob URL when it changes or the row unmounts.
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  if (count === 0 || !firstDevice) return null;

  const load = async () => {
    if (url || loading) return;
    setLoading(true);
    const u = await api.multicamClipBlobUrl(sessionId, firstDevice).catch(() => null);
    if (u) setUrl(u);
    setLoading(false);
  };

  return (
    <div className="relative h-32 w-56 shrink-0 overflow-hidden rounded-xl bg-black">
      {url ? (
        <video src={url} controls autoPlay playsInline className="h-full w-full object-contain" />
      ) : (
        <button
          onClick={load}
          className="flex h-full w-full flex-col items-center justify-center gap-1 text-neutral-300 hover:bg-white/5"
        >
          <span className="text-2xl">{loading ? "…" : "▶"}</span>
          <span className="text-[11px]">
            {loading ? "Loading…" : `Preview · ${count} camera${count === 1 ? "" : "s"}`}
          </span>
        </button>
      )}
    </div>
  );
}
