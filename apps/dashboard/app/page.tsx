async function fetchHealth(): Promise<{ status: string; schema_version: string } | null> {
  try {
    const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export default async function Home() {
  const health = await fetchHealth();
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold">Combat Intel</h1>
      <p className="mt-2 text-neutral-400">Phase 0 — skeleton.</p>
      <section className="mt-8 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-medium">API</h2>
        {health ? (
          <p className="mt-2 text-sm">
            ✓ healthy · schema {health.schema_version}
          </p>
        ) : (
          <p className="mt-2 text-sm text-amber-400">
            API unreachable. Start with <code>uv run uvicorn api.main:app --reload</code>.
          </p>
        )}
      </section>
    </main>
  );
}
