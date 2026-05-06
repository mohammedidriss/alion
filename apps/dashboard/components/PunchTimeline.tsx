"use client";

import { type PunchEvent } from "@/lib/api";

interface Props {
  events: PunchEvent[];
  durationMs: number;
}

/**
 * Horizontal timeline of punches over the session duration.
 * Each punch is a colored dot positioned at its t_ms offset; size scales
 * with peak velocity so harder punches stand out at a glance.
 *
 * Pure SVG, no chart library. Two parallel rows: left hand (top, amber)
 * and right hand (bottom, sky-blue), so combos read naturally.
 */
export function PunchTimeline({ events, durationMs }: Props) {
  if (events.length === 0 || durationMs <= 0) return null;

  const W = 600;
  const H = 80;
  const padX = 8;
  const padY = 16;
  const innerW = W - padX * 2;
  const leftY = padY + 12;
  const rightY = H - padY - 12;

  const peakV = Math.max(...events.map((e) => e.velocity_ms), 1);

  const dotR = (v: number) => {
    // Map velocity → radius 2.5..7px, square-rooted so subtle differences read.
    const norm = Math.sqrt(Math.min(1, v / peakV));
    return 2.5 + norm * 4.5;
  };

  // Tick every 5 seconds.
  const totalSec = durationMs / 1000;
  const tickEverySec = totalSec > 60 ? 10 : 5;
  const tickCount = Math.floor(totalSec / tickEverySec);
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => i * tickEverySec);

  return (
    <figure className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="block h-24 w-full"
        role="img"
        aria-label="Punch timeline"
      >
        {/* Center axis */}
        <line
          x1={padX}
          y1={H / 2}
          x2={W - padX}
          y2={H / 2}
          stroke="#404040"
          strokeWidth="1"
        />

        {/* Hand-row labels */}
        <text x={padX} y={leftY - 6} fontSize="9" fill="#fbbf24">L</text>
        <text x={padX} y={rightY + 14} fontSize="9" fill="#60a5fa">R</text>

        {/* Tick marks */}
        {ticks.map((s) => {
          const x = padX + (s / totalSec) * innerW;
          return (
            <g key={s}>
              <line
                x1={x}
                y1={H / 2 - 2}
                x2={x}
                y2={H / 2 + 2}
                stroke="#525252"
                strokeWidth="1"
              />
              <text x={x} y={H - 2} fontSize="8" fill="#737373" textAnchor="middle">
                {s}s
              </text>
            </g>
          );
        })}

        {/* Punch dots */}
        {events.map((e, i) => {
          const x = padX + Math.min(1, e.t_ms / durationMs) * innerW;
          const isLeft = e.hand === "left";
          const y = isLeft ? leftY : rightY;
          const fill = isLeft ? "#fbbf24" : "#60a5fa";
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={dotR(e.velocity_ms)}
              fill={fill}
              opacity={0.7 + 0.3 * (e.confidence ?? 0)}
            >
              <title>
                #{i + 1} · {e.hand} · {(e.t_ms / 1000).toFixed(2)}s ·{" "}
                {e.velocity_ms.toFixed(2)} m/s · conf {e.confidence?.toFixed(2)}
              </title>
            </circle>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-neutral-500">
        <span>0s</span>
        <span>dot size = velocity · {events.length} punches</span>
        <span>{totalSec.toFixed(1)}s</span>
      </figcaption>
    </figure>
  );
}
