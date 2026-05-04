"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Fighter, type SessionSource } from "@/lib/api";

export default function NewSessionPage() {
  const router = useRouter();
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [fighterId, setFighterId] = useState<string>("");
  const [source, setSource] = useState<SessionSource>("live_webcam");
  const [newFighterName, setNewFighterName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .listFighters()
      .then((fs) => {
        setFighters(fs);
        if (fs[0]) setFighterId(fs[0].id);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const createFighter = async () => {
    if (!newFighterName.trim()) return;
    const f = await api.createFighter(newFighterName.trim());
    setFighters([...fighters, f]);
    setFighterId(f.id);
    setNewFighterName("");
  };

  const submit = async () => {
    if (!fighterId) return;
    setBusy(true);
    setErr(null);
    try {
      const s = await api.createSession(fighterId, source);
      router.push(`/sessions/${s.id}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-8">
      <h1 className="text-2xl font-semibold">New session</h1>
      {err && <p className="text-sm text-red-400">{err}</p>}

      <section className="space-y-2 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-sm font-medium text-neutral-300">Fighter</h2>
        {fighters.length > 0 ? (
          <select
            className="w-full rounded bg-neutral-900 p-2 text-sm"
            value={fighterId}
            onChange={(e) => setFighterId(e.target.value)}
          >
            {fighters.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({f.stance})
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-neutral-500">No fighters yet.</p>
        )}
        <div className="mt-3 flex gap-2">
          <input
            className="flex-1 rounded bg-neutral-900 p-2 text-sm"
            placeholder="New fighter name…"
            value={newFighterName}
            onChange={(e) => setNewFighterName(e.target.value)}
          />
          <button
            onClick={createFighter}
            className="rounded bg-neutral-700 px-3 text-sm hover:bg-neutral-600"
          >
            Add fighter
          </button>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-sm font-medium text-neutral-300">Source</h2>
        <div className="flex gap-3">
          {(["live_webcam", "uploaded_video"] as SessionSource[]).map((s) => (
            <label
              key={s}
              className={`cursor-pointer rounded border px-3 py-2 text-sm ${
                source === s
                  ? "border-emerald-500 bg-emerald-900/20"
                  : "border-neutral-800"
              }`}
            >
              <input
                type="radio"
                className="hidden"
                checked={source === s}
                onChange={() => setSource(s)}
              />
              {s === "live_webcam" ? "Live webcam" : "Upload MP4"}
            </label>
          ))}
        </div>
      </section>

      <button
        onClick={submit}
        disabled={!fighterId || busy}
        className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create session"}
      </button>
    </main>
  );
}
