"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Coach } from "@/lib/api";

export default function CoachPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [coach, setCoach] = useState<Coach | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<Coach>>({});
  const [err, setErr] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getCoach(params.id)
      .then((c) => {
        setCoach(c);
        setDraft(c);
      })
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  const save = async () => {
    if (!coach) return;
    try {
      const updated = await api.updateCoach(coach.id, draft);
      setCoach(updated);
      setEditing(false);
    } catch (e) {
      setErr(String(e));
    }
  };

  const onPickPhoto = async (file: File) => {
    if (!coach) return;
    try {
      const updated = await api.uploadCoachPhoto(coach.id, file);
      setCoach(updated);
    } catch (e) {
      setErr(String(e));
    }
  };

  const remove = async () => {
    if (!coach) return;
    if (!confirm(`Delete ${coach.name}? This cannot be undone.`)) return;
    try {
      await api.deleteCoach(coach.id);
      router.push("/");
    } catch (e) {
      setErr(String(e));
    }
  };

  if (err)
    return (
      <main className="mx-auto max-w-3xl p-8 text-sm text-red-400">{err}</main>
    );
  if (!coach)
    return (
      <main className="mx-auto max-w-3xl p-8 text-sm text-neutral-400">
        Loading…
      </main>
    );

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-8 py-8">
      <Link href="/" className="text-sm text-neutral-400 hover:text-neutral-100">
        ← Back to roster
      </Link>

      <header className="flex items-start gap-5">
        <button
          onClick={() => photoInput.current?.click()}
          className="group relative"
          title="Click to change photo"
        >
          <ProfileAvatar name={coach.name} photo_path={coach.photo_path} size={96} />
          <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/60 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
            change
          </span>
        </button>
        <input
          ref={photoInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onPickPhoto(e.target.files[0])}
        />
        <div className="flex-1">
          <h1 className="text-3xl font-semibold">{coach.name}</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Coach
            {coach.gym ? ` · ${coach.gym}` : ""}
            {coach.years_experience != null
              ? ` · ${coach.years_experience} yrs experience`
              : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-1.5 text-sm hover:bg-white/[0.07]"
            >
              Edit
            </button>
          )}
          <button
            onClick={remove}
            className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/20"
          >
            Delete
          </button>
        </div>
      </header>

      <section className="card">
        <h2 className="text-base font-semibold">Profile</h2>
        {editing ? (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Name"
              value={draft.name ?? ""}
              onChange={(v) => setDraft({ ...draft, name: v })}
            />
            <Input
              label="Gym"
              value={draft.gym ?? ""}
              onChange={(v) => setDraft({ ...draft, gym: v })}
            />
            <Input
              label="Specialties"
              value={draft.specialties ?? ""}
              onChange={(v) => setDraft({ ...draft, specialties: v })}
              placeholder="head movement, defense, conditioning"
            />
            <Input
              label="Years experience"
              type="number"
              value={draft.years_experience?.toString() ?? ""}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  years_experience: v ? parseInt(v, 10) : null,
                })
              }
            />
            <div className="sm:col-span-2">
              <label className="text-xs text-neutral-400">Bio</label>
              <textarea
                rows={3}
                value={draft.bio ?? ""}
                onChange={(e) => setDraft({ ...draft, bio: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <button
                onClick={save}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setDraft(coach);
                  setEditing(false);
                }}
                className="rounded-xl bg-neutral-800 px-3 py-2 text-sm hover:bg-neutral-700"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <Field label="Gym" value={coach.gym} />
            <Field label="Specialties" value={coach.specialties} />
            <Field
              label="Years experience"
              value={coach.years_experience?.toString() ?? null}
            />
            <Field
              label="Created"
              value={new Date(coach.created_at).toLocaleString()}
            />
            <div className="sm:col-span-2">
              <dt className="text-xs text-neutral-500">Bio</dt>
              <dd className="mt-1 whitespace-pre-wrap text-sm text-neutral-200">
                {coach.bio ?? "—"}
              </dd>
            </div>
          </dl>
        )}
      </section>
    </main>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-sm">{value ?? "—"}</dd>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="text-xs text-neutral-400">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
      />
    </div>
  );
}
