"use client";

/**
 * Alion brand mark — a stylised "A" framed inside a hexagonal shield with
 * the brand gradient (violet → emerald). The right diagonal flares wider
 * at the top to suggest a punch's follow-through.
 */
export function AlionLogo({ size = 36 }: { size?: number }) {
  const id = "alion-grad";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Alion logo"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
      </defs>
      {/* Hexagonal shield */}
      <path
        d="M32 2 L57 16 L57 48 L32 62 L7 48 L7 16 Z"
        fill={`url(#${id})`}
      />
      <path
        d="M32 2 L57 16 L57 48 L32 62 L7 48 L7 16 Z"
        fill="none"
        stroke="rgba(0,0,0,0.25)"
        strokeWidth={1}
      />
      {/* Stylised A: two diagonal strokes meeting at the apex,
          right stroke flares outward (motion / punch follow-through). */}
      <g fill="#0a0a0f">
        <path d="M32 14 L20 50 L26 50 L29 41 L35 41 L38 50 L46 50 L34 14 Z" />
      </g>
      {/* Cross-bar of the A */}
      <rect x="28" y="36" width="8" height="3" fill="#0a0a0f" />
      {/* Punch dot — small fist mark in the upper-right corner */}
      <circle cx="48" cy="20" r="3" fill="#0a0a0f" />
    </svg>
  );
}

/**
 * Wordmark version — logo + "ALION" in a chunky semibold. Use for headers.
 */
export function AlionWordmark({ size = 36 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <AlionLogo size={size} />
      <span
        className="font-bold tracking-[0.18em]"
        style={{ fontSize: size * 0.62 }}
      >
        ALION
      </span>
    </span>
  );
}
