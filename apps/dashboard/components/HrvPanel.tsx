"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkline } from "@/components/Sparkline";
import {
  api,
  type HRSample,
  type HrvStatus,
} from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  sessionId: string;
}

export function HrvPanel({ sessionId }: Props) {
  const [status, setStatus] = useState<HrvStatus | null>(null);
  const [samples, setSamples] = useState<HRSample[]>([]);
  const [uploading, setUploading] = useState(false);
  const [hasCsv, setHasCsv] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [realtime, setRealtime] = useState(true);
  const evtRef = useRef<EventSource | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.hrvStatus(sessionId);
      setStatus(s);
      // The session's notes carry an `hrv_csv: ...` marker once a CSV is
      // uploaded — but we can't see that from /hrv/status. As a proxy,
      // sample_count > 0 OR is_running implies the CSV path exists.
      if (s.sample_count > 0 || s.is_running) setHasCsv(true);
    } catch (e) {
      setErr(String(e));
    }
  }, [sessionId]);

  const refreshSamples = useCallback(async () => {
    try {
      setSamples(await api.hrvSamples(sessionId));
    } catch (e) {
      setErr(String(e));
    }
  }, [sessionId]);

  useEffect(() => {
    refreshStatus();
    refreshSamples();
  }, [refreshStatus, refreshSamples]);

  // Stream live updates while running.
  useEffect(() => {
    if (!status?.is_running) return;
    const es = new EventSource(`${API_BASE}/v2/sessions/${sessionId}/hrv/live`);
    evtRef.current = es;
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as HrvStatus;
        setStatus(payload);
        // When the runner pushes new samples, refresh the chart from the API.
        if (payload.sample_count !== samples.length) refreshSamples();
        if (!payload.is_running) {
          es.close();
          evtRef.current = null;
        }
      } catch {
        // ignore malformed frames
      }
    };
    es.onerror = () => {
      es.close();
      evtRef.current = null;
    };
    return () => {
      es.close();
      evtRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.is_running, sessionId]);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      await api.uploadHrvCsv(sessionId, file);
      setHasCsv(true);
      await refreshStatus();
    } catch (e) {
      setErr(String(e));
    } finally {
      setUploading(false);
    }
  };

  const start = async () => {
    try {
      await api.startHrv(sessionId, { realtime });
      await refreshStatus();
      await refreshSamples();
    } catch (e) {
      setErr(String(e));
    }
  };

  const stop = async () => {
    try {
      await api.stopHrv(sessionId);
      await refreshStatus();
    } catch (e) {
      setErr(String(e));
    }
  };

  const hrSeries = samples.map((s) => s.hr_bpm);
  const m = status?.metrics;

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">HRV (Phase 1 Week 2)</h2>
        {status?.is_running && (
          <span className="flex items-center gap-2 text-xs text-neutral-400">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
            live
          </span>
        )}
      </div>
      {err && <p className="mt-2 text-sm text-red-400">{err}</p>}

      {/* Stats row */}
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Cell
          label="Mean HR"
          value={m ? `${m.mean_hr_bpm.toFixed(1)} bpm` : "—"}
        />
        <Cell
          label="RMSSD"
          value={m ? `${m.rmssd_ms.toFixed(1)} ms` : "—"}
        />
        <Cell label="SDNN" value={m ? `${m.sdnn_ms.toFixed(1)} ms` : "—"} />
        <Cell label="Samples" value={status?.sample_count ?? 0} />
      </dl>

      {/* HR series chart */}
      {hrSeries.length > 1 && (
        <div className="mt-4">
          <Sparkline values={hrSeries} color="#f87171" ariaLabel="HR over time" />
          <p className="mt-1 text-xs text-neutral-500">
            Heart rate (bpm) across {hrSeries.length} samples.
          </p>
        </div>
      )}

      {/* Controls */}
      <div className="mt-4 border-t border-neutral-800 pt-4">
        {!hasCsv ? (
          <div>
            <label className="text-sm font-medium text-neutral-300">
              Upload an RR-interval CSV
            </label>
            <p className="mt-1 text-xs text-neutral-500">
              One column <code>rr_ms</code> (auto-derives time) or two columns{" "}
              <code>t_ms,rr_ms</code>. Polar H10 BLE driver lands once the
              strap arrives.
            </p>
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={uploading}
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
              className="mt-2 w-full text-sm"
            />
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {!status?.is_running ? (
              <>
                <button
                  onClick={start}
                  className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
                >
                  {status && status.sample_count > 0 ? "Re-run replay" : "Start replay"}
                </button>
                <label className="flex items-center gap-2 text-xs text-neutral-400">
                  <input
                    type="checkbox"
                    checked={realtime}
                    onChange={(e) => setRealtime(e.target.checked)}
                  />
                  realtime (stream at the source's natural pace)
                </label>
              </>
            ) : (
              <button
                onClick={stop}
                className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500"
              >
                Stop replay
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Cell({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-neutral-800 p-2">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-base font-semibold">{value}</dd>
    </div>
  );
}
