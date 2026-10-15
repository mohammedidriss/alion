"use client";

import { useId } from "react";

/**
 * RingsideIQ brand mark (ADR-061) — a ring seen from ringside: two corner posts and
 * three ropes, the middle rope carrying a heartbeat (the ring, measured), on the
 * brand gradient (violet → emerald). The same drawing is app/icon.svg and the
 * phone apps' icons (public/brand/).
 */
export function RingsideLogo({ size = 36 }: { size?: number }) {
  const id = `ringside-grad-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="RingsideIQ logo">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="56" height="56" rx="14" fill={`url(#${id})`} />
      {/* Corner posts */}
      <rect x="12" y="13" width="5" height="38" rx="2.5" fill="#0a0a0f" />
      <rect x="47" y="13" width="5" height="38" rx="2.5" fill="#0a0a0f" />
      {/* Ropes; the middle one carries the pulse */}
      <g stroke="#0a0a0f" strokeWidth={3.5} strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M17 21H47" />
        <path d="M17 32H25L28.5 24L33.5 40L37 32H47" />
        <path d="M17 43H47" />
      </g>
    </svg>
  );
}

/** The mark and the name — "Ringside" with "IQ" in the brand's emerald. Use for headers. */
export function RingsideWordmark({ size = 36 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <RingsideLogo size={size} />
      <span className="font-bold tracking-tight" style={{ fontSize: size * 0.62 }}>
        Ringside<span className="text-emerald-400">IQ</span>
      </span>
    </span>
  );
}
