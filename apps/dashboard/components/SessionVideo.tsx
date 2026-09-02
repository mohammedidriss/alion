"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Plays the recorded webcam clip for a session so the coach can review the
 * punches and verify the count. The clip is fetched with auth as a blob URL
 * (a plain <video src> can't send the token).
 */
export function SessionVideo({ sessionId }: { sessionId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .sessionVideoBlobUrl(sessionId)
      .then((u) => {
        if (cancelled) {
          if (u) URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
        if (!u) setErr("No video saved for this session.");
      })
      .catch(() => setErr("Could not load the video."));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [sessionId]);

  if (err) return <p className="text-xs text-neutral-500">{err}</p>;
  if (!url) return <p className="text-xs text-neutral-500">Loading video…</p>;

  return (
    <div className="space-y-2">
      <video
        src={url}
        controls
        playsInline
        className="w-full max-w-md rounded-xl border border-white/10 bg-black"
      />
      <p className="text-xs text-neutral-500">
        Review the clip to verify the punch count against what you actually threw.
      </p>
    </div>
  );
}
