/**
 * What an administrator sees on a fighter's confidential pages: administrators
 * manage accounts, not training or health data (ADR-017). Rendered by the page's
 * outer component, so the page's own hooks always run in the same order.
 */
export function AccessRestricted({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-4 px-4 py-8 sm:px-8 sm:py-12">
      <div className="text-4xl">🔒</div>
      <h1 className="text-xl font-semibold">Access Restricted</h1>
      <p className="max-w-md text-sm text-neutral-400">{children}</p>
    </div>
  );
}
