"use client";

/**
 * Asking to join a gym with its code (ADR-055): the gym, who'd see your training,
 * its rules to accept, and who to call in an emergency. The gym approves before
 * it sees anything of your training.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type JoinPreview } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const inputCls =
  "w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none";

export default function JoinPage({ params }: { params: { code: string } }) {
  const { user } = useAuth();
  const [gym, setGym] = useState<JoinPreview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rulesOk, setRulesOk] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [relation, setRelation] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .joinPreview(params.code)
      .then(setGym)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    if (user?.role === "fighter" && user.profile_id) {
      api
        .getFighter(user.profile_id)
        .then((f) => {
          setName(f.emergency_contact_name ?? "");
          setPhone(f.emergency_contact_phone ?? "");
          setRelation(f.emergency_contact_relation ?? "");
        })
        .catch(() => undefined);
    }
  }, [params.code, user]);

  const ask = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.askToJoin(params.code, {
        accept_rules: rulesOk,
        emergency_contact_name: name.trim() || undefined,
        emergency_contact_phone: phone.trim() || undefined,
        emergency_contact_relation: relation.trim() || undefined,
      });
      setDone(
        r.status === "applied"
          ? `Asked. ${gym?.gym_name} approves your request — you'll see it under "Your gym" on your profile page.`
          : `You're in ${gym?.gym_name}.`,
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (user && user.role !== "fighter") {
    return <div className="px-4 py-8 text-neutral-400 sm:px-8">Fighters join gyms with a code. Staff are invited on the gym&apos;s Staff page.</div>;
  }
  const contactOk = !!name.trim() && !!phone.trim();
  return (
    <div className="mx-auto max-w-xl space-y-5 px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="text-2xl font-semibold">Join a gym</h1>
      {err && <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>}
      {gym && !done && (
        <div className="card space-y-4">
          <div>
            <div className="text-lg font-semibold text-neutral-100">{gym.gym_name}</div>
            {gym.gym_city && <div className="text-sm text-neutral-400">{gym.gym_city}</div>}
          </div>
          {gym.status ? (
            <p className="text-sm text-neutral-300">
              You&apos;re already {gym.status} here — see &quot;Your gym&quot; on your <Link href="/profile" className="underline">profile page</Link>.
            </p>
          ) : (
            <>
              <p className="text-xs text-neutral-300">
                Once the gym approves, its leaders{gym.leaders.length > 0 && <> ({gym.leaders.join(", ")})</>} see your training sessions,
                punches, heart rate and wrist data — never your health notes. You can leave the gym later on your profile page.
              </p>
              <fieldset className="space-y-2">
                <legend className="text-sm font-semibold text-neutral-200">Emergency contact</legend>
                <p className="text-xs text-neutral-500">Your coaches, the gym&apos;s staff and your physicians see it.</p>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className={inputCls} />
                <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" className={inputCls} />
                <input value={relation} onChange={(e) => setRelation(e.target.value)} placeholder="Relation (e.g. sister)" className={inputCls} />
              </fieldset>
              {gym.rules && (
                <div className="space-y-2">
                  <div className="text-sm font-semibold text-neutral-200">The gym&apos;s rules</div>
                  <div className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/10 bg-black/30 p-3 text-sm text-neutral-300">{gym.rules}</div>
                  <label className="flex items-center gap-2 text-sm text-neutral-300">
                    <input type="checkbox" checked={rulesOk} onChange={(e) => setRulesOk(e.target.checked)} /> I accept the gym&apos;s rules
                  </label>
                </div>
              )}
              <button
                onClick={() => void ask()}
                disabled={busy || !contactOk || (!!gym.rules && !rulesOk)}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
              >
                Ask to join
              </button>
            </>
          )}
        </div>
      )}
      {done && <p className="card text-sm text-emerald-200">{done}</p>}
    </div>
  );
}
