"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type CoachNote,
  type FighterObservationResponse,
  type PerformanceTrendItem,
  type Session,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const PERIOD_OPTIONS = [
  { label: "3 months", value: 3 },
  { label: "6 months", value: 6 },
  { label: "9 months", value: 9 },
  { label: "12 months", value: 12 },
] as const;

export default function ObservationsTab({
  params,
}: {
  params: { id: string };
}) {
  const { user } = useAuth();
  if (user?.role === "admin") {
    return (
      <div className="space-y-4 px-8 py-12">
        <div className="text-4xl">🔒</div>
        <h1 className="text-xl font-semibold">Access Restricted</h1>
        <p className="max-w-md text-sm text-neutral-400">
          Coach observations and performance trends are confidential. System
          administrators manage accounts and general information only.
        </p>
      </div>
    );
  }
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [aiData, setAiData] = useState<FighterObservationResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const [trendMonths, setTrendMonths] = useState(3);
  const [trendData, setTrendData] = useState<PerformanceTrendItem[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [coachNotes, setCoachNotes] = useState<CoachNote[]>([]);

  useEffect(() => {
    api
      .listSessions(params.id)
      .then(setSessions)
      .catch((e) => setErr(String(e)));
    api
      .listFighterCoachNotes(params.id)
      .then(setCoachNotes)
      .catch(() => setCoachNotes([]));
  }, [params.id]);

  useEffect(() => {
    setTrendLoading(true);
    api
      .performanceTrend(params.id, trendMonths)
      .then((r) => setTrendData(r.items))
      .catch(() => setTrendData([]))
      .finally(() => setTrendLoading(false));
  }, [params.id, trendMonths]);

  const annotated = sessions
    .filter((s) => s.notes && s.notes.trim().length > 0)
    .sort((a, b) => b.started_at.localeCompare(a.started_at));

  const completed = sessions.filter((s) => s.status === "completed");

  const generateAI = async () => {
    setAiLoading(true);
    setAiErr(null);
    try {
      const result = await api.generateObservations(params.id);
      setAiData(result);
    } catch (e) {
      setAiErr(String(e));
    } finally {
      setAiLoading(false);
    }
  };

  if (err)
    return <p className="text-sm text-red-400">{err}</p>;

  return (
    <div className="space-y-6 px-8 py-6">
      <header>
        <h1 className="text-2xl font-semibold">Observations</h1>
        <p className="text-sm text-neutral-400">
          AI-powered training analysis, performance trends, and coach notes.
        </p>
      </header>

      {/* ── Performance Trend Chart ── */}
      <section className="rounded-lg border border-neutral-800 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Performance Trend</h2>
            <p className="mt-0.5 text-xs text-neutral-400">
              Score, velocity, and volume over time.
              {trendData.length > 0 && ` ${trendData.length} sessions plotted.`}
            </p>
          </div>
          <select
            value={trendMonths}
            onChange={(e) => setTrendMonths(Number(e.target.value))}
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          >
            {PERIOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {trendLoading ? (
          <p className="text-xs text-neutral-500">Loading trend data...</p>
        ) : trendData.length < 2 ? (
          <p className="text-sm text-neutral-500">
            Not enough sessions in this period to chart a trend.
          </p>
        ) : (
          <TrendChart data={trendData} />
        )}
      </section>

      {/* Headline strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Sessions ({trendMonths} mo)
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {trendData.length || completed.length}
          </div>
        </div>
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Coach notes
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {coachNotes.length + annotated.length}
          </div>
        </div>
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Latest session
          </div>
          <div className="mt-1 text-sm font-semibold">
            {completed[0]
              ? new Date(completed[0].started_at).toLocaleDateString()
              : "—"}
          </div>
        </div>
        <div className="rounded-2xl border border-violet-500/30 bg-violet-500/5 p-3">
          <div className="text-[10px] uppercase tracking-wide text-violet-300/70">
            AI status
          </div>
          <div className="mt-1 text-sm font-semibold text-violet-200">
            {aiData ? "Generated" : aiLoading ? "Analyzing..." : "Ready"}
          </div>
        </div>
      </div>

      {/* ── Part 1: AI Observations ── */}
      <section className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-violet-200">
              AI Training Analysis
            </h2>
            <p className="mt-0.5 text-xs text-neutral-400">
              LLM-generated insights from {completed.length} sessions over the
              last 3 months. Analyzes velocity trends, volume, consistency, and
              recovery.
            </p>
          </div>
          <button
            onClick={generateAI}
            disabled={aiLoading || completed.length < 2}
            className="shrink-0 rounded-xl bg-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-900/30 hover:bg-violet-400 disabled:opacity-50"
          >
            {aiLoading ? "Analyzing..." : aiData ? "Regenerate" : "Generate"}
          </button>
        </div>

        {completed.length < 2 && !aiData && (
          <p className="text-sm text-neutral-400">
            Need at least 2 completed sessions to generate AI analysis.
          </p>
        )}

        {aiErr && <p className="text-sm text-red-300">{aiErr}</p>}

        {aiLoading && !aiData && (
          <div className="flex items-center gap-2 text-sm text-violet-300/80">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-violet-300/30 border-t-violet-300" />
            Analyzing {completed.length} sessions...
          </div>
        )}

        {aiData && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="rounded-lg border border-violet-500/20 bg-violet-500/10 p-4">
              <p className="text-sm text-neutral-100 leading-relaxed">
                {aiData.summary}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Observations */}
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-violet-200">
                  Observations
                </h3>
                <ul className="space-y-1.5">
                  {aiData.observations.map((o, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-white/5 bg-black/30 p-2.5 text-xs text-neutral-200"
                    >
                      <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-500/20 text-[10px] font-bold text-violet-300">
                        {i + 1}
                      </span>
                      <span>{o}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Strengths & Weaknesses */}
              <div className="space-y-4">
                {aiData.strengths.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-emerald-300">
                      Strengths
                    </h3>
                    <ul className="space-y-1.5">
                      {aiData.strengths.map((s, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-xs text-neutral-200"
                        >
                          <span className="mt-0.5 text-emerald-400">+</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiData.weaknesses.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-amber-300">
                      Areas to Improve
                    </h3>
                    <ul className="space-y-1.5">
                      {aiData.weaknesses.map((w, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs text-neutral-200"
                        >
                          <span className="mt-0.5 text-amber-400">!</span>
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            {/* Training Plan */}
            {aiData.training_plan.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-violet-200">
                  Recommended Training Plan
                </h3>
                <ul className="space-y-1.5">
                  {aiData.training_plan.map((t, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-violet-500/15 bg-violet-500/5 p-3 text-sm text-neutral-200"
                    >
                      <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-500/25 text-xs font-bold text-violet-300">
                        {i + 1}
                      </span>
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── Part 2: Coach Notes ── */}
      <section className="rounded-lg border border-neutral-800 p-5 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Coach Notes</h2>
          <p className="mt-0.5 text-xs text-neutral-400">
            Observations written by assigned coaches. Notes are created
            from the coach&apos;s profile page.
          </p>
        </div>
        {coachNotes.length === 0 && annotated.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No coach notes yet. Coaches can write notes from their profile
            page under the assigned fighters section.
          </p>
        ) : (
          <ul className="space-y-3">
            {coachNotes.map((n) => (
              <li
                key={`cn-${n.id}`}
                className="rounded-lg border border-white/5 bg-black/30 p-4"
              >
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  {n.coach_photo_path ? (
                    <img
                      src={n.coach_photo_path}
                      alt=""
                      className="h-5 w-5 rounded-full object-cover"
                    />
                  ) : (
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-[10px] font-bold text-emerald-300">
                      {n.coach_name.charAt(0)}
                    </span>
                  )}
                  <span className="font-medium text-neutral-300">
                    {n.coach_name}
                  </span>
                  <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium">
                    {new Date(n.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-neutral-100 leading-relaxed">
                  {n.content}
                </p>
              </li>
            ))}

            {/* Session-level notes (legacy) */}
            {annotated.length > 0 && coachNotes.length > 0 && (
              <li className="pt-2 text-xs text-neutral-600 border-t border-neutral-800">
                Session notes
              </li>
            )}
            {annotated.map((s) => (
              <li
                key={s.id}
                className="rounded-lg border border-white/5 bg-black/30 p-4"
              >
                <div className="flex items-center justify-between text-xs text-neutral-500">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium">
                      {new Date(s.started_at).toLocaleDateString()}
                    </span>
                    <span>
                      {s.frame_count} frames · {s.duration_ms > 0
                        ? `${(s.duration_ms / 1000).toFixed(0)}s`
                        : "—"}
                    </span>
                  </div>
                  <Link
                    href={`/sessions/${s.id}`}
                    className="text-emerald-400 hover:underline"
                  >
                    open session
                  </Link>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-neutral-100 leading-relaxed">
                  {s.notes}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* ─── SVG Line Chart ─── */

const SERIES_CONFIG = [
  { key: "score" as const, label: "Score", color: "#a78bfa" },        // violet
  { key: "peak_velocity_ms" as const, label: "Velocity (m/s)", color: "#34d399" }, // emerald
  { key: "ppm" as const, label: "PPM", color: "#fbbf24" },            // amber
];

function TrendChart({ data }: { data: PerformanceTrendItem[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [visibleSeries, setVisibleSeries] = useState<Set<string>>(
    new Set(SERIES_CONFIG.map((s) => s.key))
  );

  const toggleSeries = (key: string) => {
    setVisibleSeries((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // keep at least one
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const W = 800;
  const H = 260;
  const PL = 50; // padding left
  const PR = 20;
  const PT = 20;
  const PB = 40;
  const chartW = W - PL - PR;
  const chartH = H - PT - PB;

  // Compute per-series min/max for normalization (each series gets 0-1 range).
  const seriesData = SERIES_CONFIG.filter((s) => visibleSeries.has(s.key)).map(
    (s) => {
      const vals = data.map((d) => d[s.key] as number);
      const min = Math.min(...vals);
      const max = Math.max(...vals);
      const range = max - min || 1;
      return {
        ...s,
        vals,
        min,
        max,
        range,
        points: vals.map((v, i) => ({
          x: PL + (i / Math.max(data.length - 1, 1)) * chartW,
          y: PT + chartH - ((v - min) / range) * chartH,
        })),
      };
    }
  );

  // X-axis labels (dates).
  const labelStep = Math.max(1, Math.floor(data.length / 6));
  const xLabels = data
    .map((d, i) => ({ i, label: new Date(d.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }) }))
    .filter((_, i) => i % labelStep === 0 || i === data.length - 1);

  return (
    <div className="space-y-2">
      {/* Legend / toggles */}
      <div className="flex flex-wrap gap-3">
        {SERIES_CONFIG.map((s) => (
          <button
            key={s.key}
            onClick={() => toggleSeries(s.key)}
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-opacity ${
              visibleSeries.has(s.key) ? "opacity-100" : "opacity-40"
            }`}
            style={{ borderColor: s.color, border: "1px solid" }}
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            {s.label}
          </button>
        ))}
      </div>

      {/* SVG chart */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
      >
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            x1={PL}
            y1={PT + chartH * (1 - f)}
            x2={W - PR}
            y2={PT + chartH * (1 - f)}
            stroke="rgba(255,255,255,0.06)"
          />
        ))}

        {/* Lines */}
        {seriesData.map((s) => (
          <polyline
            key={s.key}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            points={s.points.map((p) => `${p.x},${p.y}`).join(" ")}
          />
        ))}

        {/* Dots */}
        {seriesData.map((s) =>
          s.points.map((p, i) => (
            <circle
              key={`${s.key}-${i}`}
              cx={p.x}
              cy={p.y}
              r={hover === i ? 5 : 2.5}
              fill={s.color}
              opacity={hover === i ? 1 : 0.7}
            />
          ))
        )}

        {/* Hover columns (invisible rects for mouse detection) */}
        {data.map((_, i) => {
          const x = PL + (i / Math.max(data.length - 1, 1)) * chartW;
          const colW = chartW / Math.max(data.length - 1, 1);
          return (
            <rect
              key={i}
              x={x - colW / 2}
              y={PT}
              width={colW}
              height={chartH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          );
        })}

        {/* Hover line */}
        {hover !== null && (
          <line
            x1={PL + (hover / Math.max(data.length - 1, 1)) * chartW}
            y1={PT}
            x2={PL + (hover / Math.max(data.length - 1, 1)) * chartW}
            y2={PT + chartH}
            stroke="rgba(255,255,255,0.2)"
            strokeDasharray="4 4"
          />
        )}

        {/* X-axis labels */}
        {xLabels.map(({ i, label }) => (
          <text
            key={i}
            x={PL + (i / Math.max(data.length - 1, 1)) * chartW}
            y={H - 8}
            textAnchor="middle"
            fill="rgba(255,255,255,0.35)"
            fontSize={10}
          >
            {label}
          </text>
        ))}

        {/* Y-axis labels per visible series */}
        {seriesData.map((s, si) => (
          <g key={s.key}>
            <text
              x={PL - 6}
              y={PT + 4}
              textAnchor="end"
              fill={s.color}
              fontSize={9}
              opacity={0.7}
              dy={si * 11}
            >
              {s.max.toFixed(s.key === "ppm" ? 0 : 1)}
            </text>
            <text
              x={PL - 6}
              y={PT + chartH + 4}
              textAnchor="end"
              fill={s.color}
              fontSize={9}
              opacity={0.7}
              dy={si * 11}
            >
              {s.min.toFixed(s.key === "ppm" ? 0 : 1)}
            </text>
          </g>
        ))}
      </svg>

      {/* Hover tooltip */}
      {hover !== null && data[hover] && (
        <div className="flex flex-wrap gap-4 rounded-lg border border-white/5 bg-black/50 px-3 py-2 text-xs">
          <span className="text-neutral-400">
            {new Date(data[hover].date).toLocaleDateString()}
          </span>
          <span>
            Score: <span className="font-semibold text-violet-300">{data[hover].score}</span>
          </span>
          <span>
            Velocity: <span className="font-semibold text-emerald-300">{data[hover].peak_velocity_ms} m/s</span>
          </span>
          <span>
            PPM: <span className="font-semibold text-amber-300">{data[hover].ppm}</span>
          </span>
          <span>
            Punches: <span className="font-semibold">{data[hover].punch_count}</span>
          </span>
          <span>
            Duration: <span className="font-semibold">{data[hover].duration_min} min</span>
          </span>
        </div>
      )}
    </div>
  );
}
