"use client";

/**
 * Persistent multi-camera recordings (ADR-010). Lists a session's per-device clips
 * from disk (so they show for ANY session, live or past — no in-memory roster
 * needed) and plays each back inline. Clips are fetched with auth into blob URLs.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Clip = { device_id: string; ext: string; bytes: number };

export function MulticamRecordings({ sessionId }: { sessionId: string }) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    const made: string[] = [];
    api
      .multicamClips(sessionId)
      .then(async (list) => {
        if (!alive) return;
        setClips(list);
        setLoaded(true);
        for (const c of list) {
          const u = await api.multicamClipBlobUrl(sessionId, c.device_id);
          if (u && alive) {
            made.push(u);
            setUrls((prev) => ({ ...prev, [c.device_id]: u }));
          }
        }
      })
      .catch(() => setLoaded(true));
    return () => {
      alive = false;
      made.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [sessionId]);

  if (!loaded || clips.length === 0) return null; // nothing recorded for this session

  return (
    <div className="card">
      <h2 className="mb-3 text-lg font-semibold">Camera recordings</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {clips.map((c, i) => (
          <div key={c.device_id} className="space-y-1">
            <p className="text-xs text-neutral-400">
              📷 Camera {i + 1} · {(c.bytes / 1_000_000).toFixed(1)} MB
            </p>
            {urls[c.device_id] ? (
              <video
                src={urls[c.device_id]}
                controls
                playsInline
                className="aspect-video w-full rounded-lg border border-white/10 bg-black object-contain"
              />
            ) : (
              <div className="flex aspect-video w-full items-center justify-center rounded-lg border border-white/10 bg-black text-xs text-neutral-500">
                Loading clip…
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
