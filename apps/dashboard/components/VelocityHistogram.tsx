"use client";

import { type PunchEvent } from "@/lib/api";

interface Props {
  events: PunchEvent[];
  bucketCount?: number;
}

/**
 * Histogram of punch velocities. Buckets are computed from the actual
 * data range so the chart self-scales; 8 bars by default reads well at
 * dashboard size. Bars are split left vs right per bucket so you can
 * see whether your hardest punches favor a side.
 */
export function VelocityHistogram({ events, bucketCount = 8 }: Props) {
  if (events.length === 0) return null;

  const vels = events.map((e) => e.velocity_ms);
  const min = Math.min(...vels);
  const max = Math.max(...vels);
  if (max - min < 0.01) return null; // not enough variance to bucket

  const span = max - min;
  const step = span / bucketCount;

  const buckets = Array.from({ length: bucketCount }, (_, i) => {
    const lo = min + i * step;
    const hi = i === bucketCount - 1 ? max + 1e-6 : lo + step;
    const inBucket = events.filter((e) => e.velocity_ms >= lo && e.velocity_ms < hi);
    return {
      lo,
      hi,
      total: inBucket.length,
      left: inBucket.filter((e) => e.hand === "left").length,
      right: inBucket.filter((e) => e.hand === "right").length,
    };
  });

  const peak = Math.max(...buckets.map((b) => b.total), 1);

  const W = 600;
  const H = 120;
  const padX = 8;
  const padBottom = 18;
  const padTop = 6;
  const innerW = W - padX * 2;
  const innerH = H - padBottom - padTop;
  const barW = innerW / bucketCount;

  return (
    <figure className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="block h-32 w-full"
        role="img"
        aria-label="Velocity distribution histogram"
      >
        {buckets.map((b, i) => {
          const x = padX + i * barW;
          const total = b.total;
          if (total === 0) return null;
          const fullH = (total / peak) * innerH;
          const leftH = (b.left / total) * fullH;
          const rightH = fullH - leftH;
          const yLeft = padTop + innerH - fullH;
          const yRight = yLeft + leftH;
          return (
            <g key={i}>
              <rect
                x={x + 2}
                y={yLeft}
                width={barW - 4}
                height={leftH}
                fill="#fbbf24"
                opacity={0.85}
              >
                <title>
                  {b.lo.toFixed(2)}–{b.hi.toFixed(2)} m/s · L: {b.left}
                </title>
              </rect>
              <rect
                x={x + 2}
                y={yRight}
                width={barW - 4}
                height={rightH}
                fill="#60a5fa"
                opacity={0.85}
              >
                <title>
                  {b.lo.toFixed(2)}–{b.hi.toFixed(2)} m/s · R: {b.right}
                </title>
              </rect>
              {total > 0 && (
                <text
                  x={x + barW / 2}
                  y={yLeft - 2}
                  fontSize="9"
                  fill="#a3a3a3"
                  textAnchor="middle"
                >
                  {total}
                </text>
              )}
            </g>
          );
        })}

        {/* X-axis ticks */}
        {[0, bucketCount / 2, bucketCount].map((i) => {
          const v = min + (i / bucketCount) * span;
          const x = padX + i * barW;
          return (
            <text
              key={i}
              x={x}
              y={H - 4}
              fontSize="9"
              fill="#737373"
              textAnchor={i === 0 ? "start" : i === bucketCount ? "end" : "middle"}
            >
              {v.toFixed(1)}
            </text>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-neutral-500">
        <span>velocity (m/s) →</span>
        <span>
          {events.length} punches · range {min.toFixed(2)}–{max.toFixed(2)} m/s
        </span>
        <span>amber=L · blue=R</span>
      </figcaption>
    </figure>
  );
}
