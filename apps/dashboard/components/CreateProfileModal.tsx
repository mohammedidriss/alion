"use client";

import { useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Coach, type Fighter, type Referee } from "@/lib/api";

type Kind = "fighter" | "coach" | "referee";

interface Props {
  kind: Kind;
  onClose: () => void;
  onCreated: (id: string, name: string, photo_path: string | null) => void;
}

const TITLE: Record<Kind, string> = {
  fighter: "Create fighter profile",
  coach: "Create coach profile",
  referee: "Create referee profile",
};

export function CreateProfileModal({ kind, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [stance, setStance] = useState<"orthodox" | "southpaw" | "switch">(
    "orthodox",
  );
  const [gym, setGym] = useState("");
  const [sanctioningBody, setSanctioningBody] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onPick = (f: File | null) => {
    setPhoto(f);
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhotoPreview(f ? URL.createObjectURL(f) : null);
  };

  const submit = async () => {
    if (!name.trim()) {
      setErr("Name is required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      let id: string;
      let photo_path: string | null = null;
      if (kind === "fighter") {
        const f: Fighter = await api.createFighter(name.trim(), stance);
        id = f.id;
        if (photo) {
          const updated = await api.uploadFighterPhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else if (kind === "coach") {
        const c: Coach = await api.createCoach({
          name: name.trim(),
          gym: gym.trim() || undefined,
        });
        id = c.id;
        if (photo) {
          const updated = await api.uploadCoachPhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else {
        const r: Referee = await api.createReferee({
          name: name.trim(),
          sanctioning_body: sanctioningBody.trim() || undefined,
        });
        id = r.id;
        if (photo) {
          const updated = await api.uploadRefereePhoto(id, photo);
          photo_path = updated.photo_path;
        }
      }
      onCreated(id, name.trim(), photo_path);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-2xl border border-white/5 bg-[#13131a] p-5 shadow-xl">
        <h3 className="text-lg font-semibold">{TITLE[kind]}</h3>

        {err && (
          <p className="mt-3 rounded-xl border border-red-500/30 bg-red-950/30 p-2 text-sm text-red-200">
            {err}
          </p>
        )}

        <div className="mt-4 flex items-start gap-4">
          {photoPreview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={photoPreview}
              alt="preview"
              className="h-20 w-20 shrink-0 rounded-full object-cover"
            />
          ) : (
            <ProfileAvatar
              name={name || "?"}
              photo_path={null}
              size={80}
            />
          )}
          <div className="flex-1">
            <label className="text-xs text-neutral-400">Photo (optional)</label>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => onPick(e.target.files?.[0] ?? null)}
              className="mt-1 w-full text-xs"
            />
            <p className="mt-1 text-[11px] text-neutral-500">
              JPG / PNG / WebP, max 5 MB.
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-neutral-400">Name *</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-violet-500/50 focus:outline-none"
              placeholder="Full name"
            />
          </div>

          {kind === "fighter" && (
            <div>
              <label className="text-xs text-neutral-400">Stance</label>
              <select
                value={stance}
                onChange={(e) => setStance(e.target.value as typeof stance)}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
              >
                <option value="orthodox">orthodox</option>
                <option value="southpaw">southpaw</option>
                <option value="switch">switch</option>
              </select>
            </div>
          )}

          {kind === "coach" && (
            <div>
              <label className="text-xs text-neutral-400">Gym (optional)</label>
              <input
                value={gym}
                onChange={(e) => setGym(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
                placeholder="e.g. Iron Gym"
              />
            </div>
          )}

          {kind === "referee" && (
            <div>
              <label className="text-xs text-neutral-400">
                Sanctioning body (optional)
              </label>
              <input
                value={sanctioningBody}
                onChange={(e) => setSanctioningBody(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
                placeholder="e.g. USA Boxing"
              />
            </div>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-xl bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || !name.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-1.5 text-sm font-medium text-black hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
          >
            {busy ? "Creating…" : "Create profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
