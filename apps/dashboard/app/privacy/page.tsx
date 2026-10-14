"use client";

/**
 * Privacy and consent (ADR-033): where your data lives, what Alion keeps about
 * you, who can see it, what you agreed to — and asking for a copy, a deletion,
 * or to leave the research datasets.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { GymInvitationsCard } from "@/components/GymInvitationsCard";
import { MyGymsCard } from "@/components/MyGymsCard";
import { api, type DataRequestKind, type PrivacyMe } from "@/lib/api";

const REQUESTS: { kind: DataRequestKind; title: string; text: string }[] = [
  {
    kind: "export",
    title: "Get a copy of my data",
    text: "Everything Alion keeps about you, sent to you once it's been checked.",
  },
  {
    kind: "withdraw",
    title: "Leave the research datasets",
    text: "Your recordings come out of the research datasets; what's already been published can't be recalled.",
  },
  {
    kind: "delete",
    title: "Delete my account and data",
    text: "Your account, sessions, sensor data and health notes are deleted. This can't be undone.",
  },
];

const KIND_LABEL: Record<DataRequestKind, string> = {
  export: "Copy of my data",
  withdraw: "Leave the research datasets",
  delete: "Delete my account and data",
};

const CONSENT_LABEL: Record<string, string> = {
  self: "researcher recording themself",
  irb_signed: "signed consent form",
  pending: "consent not yet recorded",
  withdrawn: "withdrawn",
};

function detail(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/^(\d{3}) ([\s\S]*)$/);
  try {
    return m ? String(JSON.parse(m[2]).detail ?? raw) : raw;
  } catch {
    return raw;
  }
}

export default function PrivacyPage() {
  const [me, setMe] = useState<PrivacyMe | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [asking, setAsking] = useState<DataRequestKind | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.privacyMe().then(setMe).catch((e) => setErr(detail(e)));
  }, []);
  useEffect(() => load(), [load]);

  const send = async (kind: DataRequestKind) => {
    setBusy(true);
    setErr(null);
    try {
      await api.privacyRequest(kind, note.trim() || undefined);
      setAsking(null);
      setNote("");
      load();
    } catch (e) {
      setErr(detail(e));
    } finally {
      setBusy(false);
    }
  };

  const open = new Set(me?.requests.filter((r) => r.status === "open").map((r) => r.kind));

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Privacy &amp; consent</h1>
        <p className="text-sm text-neutral-300">
          What Alion keeps about you, who can see it, what you agreed to — and how to ask for a
          copy, a deletion, or to leave the research.
        </p>
      </header>
      {err && <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>}

      <section className="card space-y-2 text-sm text-neutral-200">
        <h2 className="text-base font-semibold">Where your data lives</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>On this computer — in Alion&apos;s own database and folders, not in a cloud service.</li>
          <li>
            The AI training advice is written on this computer or another one on the same network;
            nothing is sent to an outside AI service.
          </li>
          <li>
            Research datasets name you by a code, never your name, and their videos are exported with
            faces blurred.
          </li>
          <li>Every look at your health notes is logged, with who looked and when.</li>
          {me?.disk_encrypted === "on" && (
            <li>This computer&apos;s disk is encrypted (FileVault is on), so the data is unreadable if the computer is lost.</li>
          )}
          {me?.disk_encrypted === "off" && (
            <li className="text-amber-200">
              This computer&apos;s disk isn&apos;t encrypted. Whoever runs Alion should turn on FileVault in
              System Settings → Privacy &amp; Security.
            </li>
          )}
        </ul>
      </section>

      {me && (
        <section className="card space-y-2">
          <h2 className="text-base font-semibold">What Alion keeps about you</h2>
          <ul className="divide-y divide-white/5 text-sm">
            {me.holdings.map((h) => (
              <li key={h.what} className="flex justify-between gap-3 py-1.5">
                <span className="text-neutral-200">{h.what}</span>
                <span className="tabular-nums text-neutral-300">{h.what.startsWith("Your account") ? "" : h.count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {me?.viewers && <GymInvitationsCard onAnswered={load} />}
      {me?.viewers && <MyGymsCard onChanged={load} />}

      <section className="card space-y-3 text-sm">
        <h2 className="text-base font-semibold">Who can see it</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px]">
            <thead className="text-left text-xs uppercase text-neutral-400">
              <tr>
                <th className="py-1.5 pr-3">Who</th>
                <th className="py-1.5 pr-3">Training data</th>
                <th className="py-1.5">Health notes</th>
              </tr>
            </thead>
            <tbody className="text-neutral-200">
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">You</td><td>Yes</td><td>Yes</td></tr>
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">Your current coaches</td><td>Yes</td><td>Only if you share them (Team page)</td></tr>
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">Physicians you choose</td><td>Yes, to read</td><td>Yes</td></tr>
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">Managers of gyms you joined</td><td>Yes, once you accept</td><td>No</td></tr>
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">The researcher running the study</td><td>Yes, all of it</td><td>Yes — every look is logged</td></tr>
              <tr className="border-t border-white/5"><td className="py-1.5 pr-3">Administrators</td><td>No — accounts only</td><td>No</td></tr>
            </tbody>
          </table>
        </div>
        {me?.viewers && (
          <p className="text-neutral-300">
            Right now:{" "}
            {me.viewers.coaches.length ? <>coaches <b>{me.viewers.coaches.join(", ")}</b></> : "no coach"}
            {me.viewers.coaches_with_health && me.viewers.coaches_with_health.length > 0 && (
              <> (health notes shared with {me.viewers.coaches_with_health.join(", ")})</>
            )}
            {" · "}
            {me.viewers.physicians && me.viewers.physicians.length ? (
              <>physicians <b>{me.viewers.physicians.join(", ")}</b></>
            ) : (
              "no physician"
            )}
            {" · "}
            {me.viewers.gyms.length ? (
              <>
                gym <b>{me.viewers.gyms.join(", ")}</b>
                {me.viewers.gym_managers.length > 0 && <> (managed by {me.viewers.gym_managers.join(", ")})</>}
              </>
            ) : (
              "no gym"
            )}
            .
          </p>
        )}
      </section>

      {me && (
        <section className="card space-y-2 text-sm">
          <h2 className="text-base font-semibold">What you agreed to</h2>
          <p className="text-neutral-200">
            {me.terms_version ? (
              <>
                Terms and conditions <b>{me.terms_version}</b>
                {me.terms_accepted_at && <>, accepted {new Date(me.terms_accepted_at).toLocaleDateString()}</>}.{" "}
              </>
            ) : (
              "No terms accepted yet. "
            )}
            <Link href="/terms" className="text-emerald-400 hover:underline">
              Read them
            </Link>
          </p>
          {me.datasets.length > 0 ? (
            <ul className="space-y-1 text-neutral-200">
              {me.datasets.map((d) => (
                <li key={d.dataset}>
                  Research dataset <b>{d.dataset}</b> as <b className="font-mono">{d.code ?? "—"}</b> —{" "}
                  {CONSENT_LABEL[d.consent] ?? d.consent}
                  {d.consent_date && `, ${new Date(d.consent_date).toLocaleDateString()}`}
                </li>
              ))}
            </ul>
          ) : (
            me.viewers && <p className="text-neutral-400">You&apos;re not in any research dataset.</p>
          )}
        </section>
      )}

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">Ask for something</h2>
        <p className="text-sm text-neutral-300">
          A person handles each request and writes back here — usually within a few days.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {REQUESTS.map((r) => (
            <div key={r.kind} className="flex flex-col justify-between gap-2 rounded-xl border border-white/10 p-3">
              <div>
                <h3 className="text-sm font-semibold text-neutral-100">{r.title}</h3>
                <p className="mt-1 text-xs text-neutral-400">{r.text}</p>
              </div>
              {open.has(r.kind) ? (
                <span className="text-xs text-amber-300">Asked — waiting for a reply</span>
              ) : (
                <button
                  onClick={() => {
                    setAsking(r.kind);
                    setNote("");
                  }}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                    r.kind === "delete"
                      ? "border border-red-500/40 text-red-200 hover:bg-red-500/10"
                      : "border border-white/15 text-neutral-100 hover:bg-white/5"
                  }`}
                >
                  Ask
                </button>
              )}
            </div>
          ))}
        </div>
        {asking && (
          <div className="space-y-2 rounded-xl border border-white/15 p-3">
            <p className="text-sm text-neutral-200">
              <b>{KIND_LABEL[asking]}</b> — anything the person handling it should know? (optional)
            </p>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={2000}
              className="w-full rounded-xl border border-white/10 bg-black/30 p-2 text-sm outline-none focus:border-emerald-500/50"
            />
            <div className="flex gap-2">
              <button
                onClick={() => void send(asking)}
                disabled={busy}
                className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
              >
                {busy ? "Sending…" : "Send request"}
              </button>
              <button onClick={() => setAsking(null)} className="text-sm text-neutral-400 hover:text-neutral-200">
                Cancel
              </button>
            </div>
          </div>
        )}
        {me && me.requests.length > 0 && (
          <ul className="divide-y divide-white/5 text-sm">
            {me.requests.map((r) => (
              <li key={r.id} className="py-2">
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="text-neutral-100">{KIND_LABEL[r.kind]}</span>
                  <span
                    className={
                      r.status === "open" ? "text-amber-300" : r.status === "done" ? "text-emerald-300" : "text-neutral-400"
                    }
                  >
                    {r.status === "open" ? "waiting" : r.status} · {new Date(r.created_at).toLocaleDateString()}
                  </span>
                </div>
                {r.response && <p className="mt-0.5 text-xs text-neutral-300">Reply: {r.response}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
