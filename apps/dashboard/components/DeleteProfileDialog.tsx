"use client";

/**
 * Deleting a fighter's profile (ADR-056): recordings are never deleted. Two choices —
 * delete the profile (and its login), keeping every recording with its heart-rate
 * and wrist-sensor data; or delete the login only, keeping the profile and the
 * recordings where they are. The server says which this viewer may do.
 */

import { useEffect, useState } from "react";
import { api, type FighterRemoval } from "@/lib/api";

type Choice = "profile" | "account";

export function DeleteProfileDialog({
  fighterId,
  fighterName,
  onCancel,
  onDone,
}: {
  fighterId: string;
  fighterName: string;
  onCancel: () => void;
  onDone: (choice: Choice) => void;
}) {
  const [opts, setOpts] = useState<FighterRemoval | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .fighterRemoval(fighterId)
      .then((o) => {
        setOpts(o);
        setChoice(o.can_delete_profile ? "profile" : o.can_delete_account ? "account" : null);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [fighterId]);

  const go = async () => {
    if (!choice) return;
    setBusy(true);
    setErr(null);
    try {
      if (choice === "profile") await api.deleteFighter(fighterId);
      else await api.deleteFighterAccount(fighterId);
      onDone(choice);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const option = (value: Choice, title: string, body: string, enabled: boolean) => (
    <label
      className={`flex gap-3 rounded-xl border p-3 text-sm ${
        choice === value ? "border-red-500/40 bg-red-950/20" : "border-white/10"
      } ${enabled ? "cursor-pointer" : "opacity-40"}`}
    >
      <input type="radio" disabled={!enabled} checked={choice === value} onChange={() => setChoice(value)} className="mt-1" />
      <span>
        <span className="font-medium text-neutral-100">{title}</span>
        <span className="mt-0.5 block text-xs text-neutral-400">{body}</span>
      </span>
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-lg space-y-4 rounded-2xl border border-white/5 bg-[#13131a] p-5 shadow-xl">
        <h3 className="font-medium">Delete {fighterName}&apos;s profile</h3>
        <p className="text-xs text-neutral-400">
          Recordings are never deleted: every session, its video, heart-rate and wrist-sensor data stay, for the study
          and the models.
        </p>
        {opts && (
          <div className="space-y-2">
            {option(
              "profile",
              "Delete the profile, keep the recordings",
              (opts.has_account ? "The profile and its login go: nobody signs in to it, " : "The profile goes: ") +
                "it disappears from every list, and its coaches, physicians, gyms and squads let it go. " +
                "The recordings, heart rate and wrist-sensor data are kept. An administrator can restore it.",
              opts.can_delete_profile,
            )}
            {opts.has_account &&
              option(
                "account",
                "Delete the login account only",
                "Nobody signs in to it any more and its email is free again. The profile and its recordings stay as they are.",
                opts.can_delete_account,
              )}
            {opts.note && <p className="text-xs text-amber-300">{opts.note}</p>}
          </div>
        )}
        {choice && (
          <div>
            <label className="text-xs text-neutral-400">
              Type <span className="font-mono text-red-300">{fighterName}</span> to confirm
            </label>
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-red-500/50 focus:outline-none"
              placeholder={fighterName}
            />
          </div>
        )}
        {err && <p className="text-sm text-red-300">{err}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-xl bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">
            Cancel
          </button>
          <button
            onClick={() => void go()}
            disabled={!choice || typed !== fighterName || busy}
            className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-red-900/40 disabled:text-red-300/50"
          >
            {choice === "account" ? "Delete the login" : "Delete the profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
