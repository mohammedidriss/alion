/**
 * The safety boundary, beside every readiness, heart-rate, wrist-force and health
 * output (ADR-024): RingsideIQ supports training. It never diagnoses, clears a fighter
 * to train or fight, advises on return to play, or decides a stoppage — a
 * qualified person does. (AI advice carries its own notice, <AdviceNotice>.)
 */
export function SafetyBoundary({ className = "" }: { className?: string }) {
  return (
    <p className={`flex items-start gap-1.5 text-xs leading-snug text-amber-200/90 ${className}`}>
      <span aria-hidden>⚠︎</span>
      <span>
        Training support only — not medical advice. RingsideIQ can&apos;t diagnose, clear a fighter to
        train or fight, advise on return to play, or decide a stoppage; a qualified person does.
      </span>
    </p>
  );
}
