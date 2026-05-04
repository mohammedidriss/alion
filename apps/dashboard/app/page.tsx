import Link from "next/link";
import { type Fighter, type Session } from "@/lib/api";

export const dynamic = "force-dynamic";

// Server-side fetches go through INTERNAL_API_URL (e.g. http://api:8000 in
// docker-compose). Client-side code in /lib/api.ts uses NEXT_PUBLIC_API_URL.
const SSR_BASE =
  process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function safeJson<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${SSR_BASE}${path}`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export default async function Home() {
  const [health, sessions, fighters] = await Promise.all([
    safeJson<{ status: string; schema_version: string }>("/health"),
    safeJson<Session[]>("/sessions"),
    safeJson<Fighter[]>("/fighters"),
  ]);

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="text-3xl font-semibold">Alion</h1>
        <p className="mt-1 text-neutral-400">Phase 1 — single-stream CV capture.</p>
      </header>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">API</h2>
        {health ? (
          <p className="mt-1 text-sm text-emerald-400">
            ✓ healthy · schema {health.schema_version}
          </p>
        ) : (
          <p className="mt-1 text-sm text-amber-400">
            API unreachable — start with{" "}
            <code className="text-amber-200">uv run uvicorn api.main:app --reload</code>.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Sessions</h2>
          <Link
            href="/sessions/new"
            className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium hover:bg-emerald-500"
          >
            New session
          </Link>
        </div>
        {sessions && sessions.length > 0 ? (
          <ul className="mt-3 divide-y divide-neutral-800">
            {sessions.map((s) => (
              <li key={s.id} className="py-2 text-sm">
                <Link href={`/sessions/${s.id}`} className="hover:underline">
                  <span className="font-mono text-xs text-neutral-500">
                    {s.id.slice(0, 8)}
                  </span>{" "}
                  · {s.source} · <span className="text-neutral-400">{s.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">No sessions yet.</p>
        )}
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">Fighters</h2>
        {fighters && fighters.length > 0 ? (
          <ul className="mt-2 text-sm text-neutral-300">
            {fighters.map((f) => (
              <li key={f.id} className="font-mono text-xs">
                {f.id.slice(0, 8)} · {f.name} · {f.stance}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">No fighters yet.</p>
        )}
      </section>
    </main>
  );
}
