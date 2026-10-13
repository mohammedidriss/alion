/**
 * Shown with every piece of AI advice (ADR-018): it's an early version that can
 * be wrong, it never makes medical or fight decisions, and a person decides.
 */
export function AdviceNotice({ withheld = false }: { withheld?: boolean }) {
  return (
    <p className="mt-2 text-[11px] leading-snug text-neutral-500">
      {withheld
        ? "The safety check withheld this advice. "
        : "AI training advice from an early version — it can be wrong. "}
      Never a diagnosis, a medical clearance, or a call to stop or continue. A person makes
      every decision.
    </p>
  );
}
