"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Coach, type CoachingLevel } from "@/lib/api";

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
      <main className="mx-auto max-w-4xl p-8 text-sm text-red-400">{err}</main>
    );
  if (!coach)
    return (
      <main className="mx-auto max-w-4xl p-8 text-sm text-neutral-400">
        Loading…
      </main>
    );

  const set = <K extends keyof Coach>(k: K, v: Coach[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-8 py-8">
      <Link href="/" className="text-sm text-neutral-400 hover:text-neutral-100">
        ← Main page
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
            {coach.coaching_level ? ` · ${coach.coaching_level}` : ""}
            {coach.gym ? ` · ${coach.gym}` : ""}
            {coach.years_experience != null
              ? ` · ${coach.years_experience} yrs experience`
              : ""}
          </p>
          {(coach.email || coach.phone) && (
            <p className="mt-1 text-xs text-neutral-500">
              {coach.email && <span>{coach.email}</span>}
              {coach.email && coach.phone && " · "}
              {coach.phone && <span>{coach.phone}</span>}
            </p>
          )}
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

      {editing ? (
        <section className="card space-y-5">
          <h2 className="text-base font-semibold">Edit profile</h2>

          <Group title="Identity">
            <Input label="Name" value={draft.name ?? ""} onChange={(v) => set("name", v)} />
            <Input
              label="Date of birth"
              type="date"
              value={draft.dob ?? ""}
              onChange={(v) => set("dob", v || null)}
            />
            <Input
              label="Nationality"
              value={draft.nationality ?? ""}
              onChange={(v) => set("nationality", v || null)}
            />
            <Select
              label="Sex"
              value={draft.sex ?? ""}
              onChange={(v) => set("sex", v || null)}
              options={[
                { value: "", label: "—" },
                { value: "male", label: "male" },
                { value: "female", label: "female" },
                { value: "other", label: "other" },
              ]}
            />
          </Group>

          <Group title="Contact">
            <Input
              label="Email"
              type="email"
              value={draft.email ?? ""}
              onChange={(v) => set("email", v || null)}
            />
            <Input
              label="Phone"
              value={draft.phone ?? ""}
              onChange={(v) => set("phone", v || null)}
            />
          </Group>

          <Group title="Coaching">
            <Input
              label="Gym"
              value={draft.gym ?? ""}
              onChange={(v) => set("gym", v || null)}
            />
            <Input
              label="Specialties"
              value={draft.specialties ?? ""}
              onChange={(v) => set("specialties", v || null)}
              placeholder="head movement, defense, conditioning"
            />
            <Select
              label="Coaching level"
              value={draft.coaching_level ?? ""}
              onChange={(v) =>
                set("coaching_level", (v || null) as CoachingLevel | null)
              }
              options={[
                { value: "", label: "—" },
                { value: "amateur", label: "amateur" },
                { value: "professional", label: "professional" },
                { value: "both", label: "both" },
              ]}
            />
            <Input
              label="Years experience"
              type="number"
              value={draft.years_experience?.toString() ?? ""}
              onChange={(v) => set("years_experience", v ? parseInt(v, 10) : null)}
            />
          </Group>

          <Group title="Credentials">
            <Input
              label="Certifications"
              value={draft.certifications ?? ""}
              onChange={(v) => set("certifications", v || null)}
              placeholder="USA Boxing Level 2, AIBA 1-Star"
            />
            <Input
              label="License number"
              value={draft.license_number ?? ""}
              onChange={(v) => set("license_number", v || null)}
            />
            <Input
              label="License expiry"
              type="date"
              value={draft.license_expiry ?? ""}
              onChange={(v) => set("license_expiry", v || null)}
            />
            <Input
              label="Languages"
              value={draft.languages ?? ""}
              onChange={(v) => set("languages", v || null)}
              placeholder="English, Spanish"
            />
          </Group>

          <Group title="Track record">
            <Textarea
              label="Notable fighters trained"
              value={draft.notable_fighters ?? ""}
              onChange={(v) => set("notable_fighters", v || null)}
              rows={2}
            />
            <Textarea
              label="Bio"
              value={draft.bio ?? ""}
              onChange={(v) => set("bio", v || null)}
              rows={4}
            />
          </Group>

          <div className="flex gap-2">
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
        </section>
      ) : (
        <>
          <section className="card">
            <h2 className="text-base font-semibold">Identity</h2>
            <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
              <Field label="Date of birth" value={fmtDate(coach.dob)} />
              <Field label="Nationality" value={coach.nationality} />
              <Field label="Sex" value={coach.sex} />
              <Field label="Email" value={coach.email} />
              <Field label="Phone" value={coach.phone} />
              <Field
                label="Created"
                value={new Date(coach.created_at).toLocaleString()}
              />
            </dl>
          </section>

          <section className="card">
            <h2 className="text-base font-semibold">Coaching</h2>
            <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
              <Field label="Gym" value={coach.gym} />
              <Field label="Coaching level" value={coach.coaching_level} />
              <Field
                label="Years experience"
                value={coach.years_experience?.toString() ?? null}
              />
              <div className="sm:col-span-3">
                <dt className="text-xs text-neutral-500">Specialties</dt>
                <dd className="mt-0.5 text-sm">{coach.specialties ?? "—"}</dd>
              </div>
            </dl>
          </section>

          <section className="card">
            <h2 className="text-base font-semibold">Credentials</h2>
            <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
              <Field label="License number" value={coach.license_number} />
              <Field
                label="License expiry"
                value={fmtDate(coach.license_expiry)}
              />
              <Field label="Languages" value={coach.languages} />
              <div className="sm:col-span-3">
                <dt className="text-xs text-neutral-500">Certifications</dt>
                <dd className="mt-0.5 text-sm">{coach.certifications ?? "—"}</dd>
              </div>
            </dl>
          </section>

          <section className="card">
            <h2 className="text-base font-semibold">Track record</h2>
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <div className="text-xs text-neutral-500">
                  Notable fighters trained
                </div>
                <p className="mt-0.5 whitespace-pre-wrap">
                  {coach.notable_fighters ?? "—"}
                </p>
              </div>
              <div>
                <div className="text-xs text-neutral-500">Bio</div>
                <p className="mt-0.5 whitespace-pre-wrap">{coach.bio ?? "—"}</p>
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function fmtDate(d: string | null): string | null {
  if (!d) return null;
  return new Date(d).toLocaleDateString();
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-sm">{value ?? "—"}</dd>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
        {title}
      </h3>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">{children}</div>
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
        className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-violet-500/50 focus:outline-none"
      />
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="text-xs text-neutral-400">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Textarea({
  label,
  value,
  onChange,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div className="sm:col-span-2">
      <label className="text-xs text-neutral-400">{label}</label>
      <textarea
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
      />
    </div>
  );
}
