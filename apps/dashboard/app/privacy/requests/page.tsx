"use client";

/**
 * Data requests (ADR-033): admins and researchers see everyone's requests — a
 * copy of their data, a deletion, leaving the research datasets — and close each
 * with a reply the person reads on their Privacy & consent page.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type DataRequestKind, type HandledDataRequest } from "@/lib/api";

const KIND_LABEL: Record<DataRequestKind, string> = {
  export: "Copy of their data",
  withdraw: "Leave the research datasets",
  delete: "Delete account and data",
};

export default function DataRequestsPage() {
  const [rows, setRows] = useState<HandledDataRequest[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reply, setReply] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api
      .privacyRequests()
      .then(setRows)
      .catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  }, []);
  useEffect(() => load(), [load]);

  const close = async (id: string, status: "done" | "declined") => {
    const text = (reply[id] ?? "").trim();
    if (!text) {
      setErr("Write a reply first — the person reads it.");
      return;
    }
    setErr(null);
    try {
      await api.closePrivacyRequest(id, status, text);
      load();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    }
  };

  const open = rows?.filter((r) => r.status === "open") ?? [];
  const closed = rows?.filter((r) => r.status !== "open") ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Data requests</h1>
        <p className="text-sm text-neutral-300">
          People asking for a copy of their data, its deletion, or to leave the research datasets.
          Do what&apos;s asked (or explain why not), then close it with a reply.
        </p>
      </header>
      {err && <p className="text-sm text-red-300">{err}</p>}
      {rows === null && !err && <p className="text-sm text-neutral-400">Loading…</p>}
      {rows && open.length === 0 && <p className="card text-sm text-neutral-300">No open requests.</p>}
      {open.map((r) => (
        <div key={r.id} className="card space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold">{KIND_LABEL[r.kind]}</h2>
            <span className="text-xs text-neutral-400">{new Date(r.created_at).toLocaleString()}</span>
          </div>
          <p className="text-sm text-neutral-200">
            {r.user_name} · {r.user_email} · {r.user_role}
          </p>
          {r.note && <p className="text-sm text-neutral-300">&ldquo;{r.note}&rdquo;</p>}
          <textarea
            value={reply[r.id] ?? ""}
            onChange={(e) => setReply((x) => ({ ...x, [r.id]: e.target.value }))}
            rows={2}
            maxLength={2000}
            placeholder="Your reply — what was done, or why not"
            className="w-full rounded-xl border border-white/10 bg-black/30 p-2 text-sm outline-none focus:border-emerald-500/50"
          />
          <div className="flex gap-2">
            <button
              onClick={() => void close(r.id, "done")}
              className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
            >
              Done
            </button>
            <button
              onClick={() => void close(r.id, "declined")}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
            >
              Decline
            </button>
          </div>
        </div>
      ))}
      {closed.length > 0 && (
        <details className="card">
          <summary className="cursor-pointer text-sm font-medium text-neutral-200">Closed ({closed.length})</summary>
          <ul className="mt-2 divide-y divide-white/5 text-sm">
            {closed.map((r) => (
              <li key={r.id} className="py-2">
                <span className="text-neutral-100">{KIND_LABEL[r.kind]}</span> — {r.user_name} ·{" "}
                <span className={r.status === "done" ? "text-emerald-300" : "text-neutral-400"}>{r.status}</span>
                {r.response && <p className="text-xs text-neutral-400">Reply: {r.response}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
