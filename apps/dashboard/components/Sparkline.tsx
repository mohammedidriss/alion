"use client";

interface Props {
  values: number[];
  labels?: string[];
  color?: string;
  height?: number;
  ariaLabel?: string;
}

export function Sparkline({
  values,
  labels,
  color = "#34d399",
  height = 80,
  ariaLabel,
}: Props) {
  if (values.length === 0) {
    return (
      <p className="text-sm text-neutral-500">Not enough data yet.</p>
    );
  }
  const w = 600;
  const h = height;
  const pad = 4;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = max - min || 1;
  const stepX = values.length > 1 ? (w - pad * 2) / (values.length - 1) : 0;
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  const path = `M${points.join(" L")}`;
  const lastIdx = values.length - 1;

  return (
    <figure className="w-full" aria-label={ariaLabel}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="block h-20 w-full"
      >
        <path d={path} fill="none" stroke={color} strokeWidth="2" />
        {/* Last-value dot */}
        <circle
          cx={pad + lastIdx * stepX}
          cy={h - pad - ((values[lastIdx] - min) / range) * (h - pad * 2)}
          r="3"
          fill={color}
        />
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-neutral-500">
        <span>{labels?.[0] ?? "first"}</span>
        <span>min {min.toFixed(1)} · max {max.toFixed(1)}</span>
        <span>{labels?.[labels.length - 1] ?? "latest"}</span>
      </figcaption>
    </figure>
  );
}
