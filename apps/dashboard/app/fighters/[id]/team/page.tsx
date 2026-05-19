"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type CoachAssignment,
  type CoachRole,
  type Fighter,
  type FighterSponsor,
  type FighterTitle,
  type TitleStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLE_LABELS: Record<CoachRole, string> = {
  head_coach: "Head coach",
  striking: "Striking",
  strength: "Strength",
  conditioning: "Conditioning",
  nutrition: "Nutrition",
  cutman: "Cutman",
  mental: "Mental",
  other: "Other",
};

const STATUS_TINT: Record<TitleStatus, string> = {
  active: "bg-emerald-500/15 text-emerald-300",
  lost: "bg-red-500/15 text-red-300",
  vacated: "bg-amber-500/15 text-amber-300",
  retired: "bg-neutral-500/15 text-neutral-300",
};


export default function TeamTab({ params }: { params: { id: string } }) {
  const fighterId = params.id;
  const { user } = useAuth();
  const readOnly = user?.role === "gym_manager";
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [titles, setTitles] = useState<FighterTitle[]>([]);
  const [sponsors, setSponsors] = useState<FighterSponsor[]>([]);
  const [coaches, setCoaches] = useState<CoachAssignment[]>([]);
  const [allCoaches, setAllCoaches] = useState<Coach[]>([]);
  const [editingBio, setEditingBio] = useState(false);
  const [draftBio, setDraftBio] = useState("");
  const [draftCareer, setDraftCareer] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [f, t, s, c, co] = await Promise.all([
        api.getFighter(fighterId),
        api.listTitles(fighterId),
        api.listSponsors(fighterId),
        api.listCoachAssignments(fighterId),
        api.listCoaches(),
      ]);
      setFighter(f);
      setTitles(t);
      setSponsors(s);
      setCoaches(c);
      setAllCoaches(co);
      if (!editingBio) {
        setDraftBio(f.bio ?? "");
        setDraftCareer(f.career_history ?? "");
      }
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, [fighterId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err)
    return <p className="text-sm text-red-400">{err}</p>;
  if (!fighter)
    return <p className="text-sm text-neutral-400">Loading…</p>;

  const saveBio = async () => {
    try {
      const updated = await api.updateFighter(fighterId, {
        bio: draftBio || null,
        career_history: draftCareer || null,
      });
      setFighter(updated);
      setEditingBio(false);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div className="space-y-6 px-8 py-6">
      <header>
        <h1 className="text-2xl font-semibold">Team</h1>
        <p className="text-sm text-neutral-400">
          Bio · gym &amp; coaches · titles · sponsors · career history
        </p>
      </header>

      {/* BIO + CAREER HISTORY */}
      <section className="card">
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold">Bio</h2>
          {!editingBio && !readOnly && (
            <button
              onClick={() => setEditingBio(true)}
              className="text-xs text-emerald-400 hover:underline"
            >
              edit
            </button>
          )}
        </div>
        {editingBio ? (
          <div className="mt-3 space-y-3">
            <div>
              <label className="text-xs text-neutral-400">
                Short bio (1–3 sentences)
              </label>
              <textarea
                rows={3}
                value={draftBio}
                onChange={(e) => setDraftBio(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
                placeholder="e.g. Former amateur national champion turned pro in 2024…"
              />
            </div>
            <div>
              <label className="text-xs text-neutral-400">
                Career history (long-form)
              </label>
              <textarea
                rows={6}
                value={draftCareer}
                onChange={(e) => setDraftCareer(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
                placeholder="Year-by-year: amateur record, key wins/losses, notable bouts, training history."
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={saveBio}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setDraftBio(fighter.bio ?? "");
                  setDraftCareer(fighter.career_history ?? "");
                  setEditingBio(false);
                }}
                className="rounded-xl bg-neutral-800 px-3 py-2 text-sm hover:bg-neutral-700"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-3 space-y-3 text-sm">
            <p className="whitespace-pre-wrap">{fighter.bio ?? "—"}</p>
            {fighter.career_history && (
              <div>
                <div className="mt-3 text-xs uppercase tracking-wide text-neutral-500">
                  Career history
                </div>
                <p className="mt-1 whitespace-pre-wrap text-neutral-300">
                  {fighter.career_history}
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* GYM + COACHES */}
      <CoachesSection
        fighter={fighter}
        coaches={coaches}
        allCoaches={allCoaches}
        readOnly={readOnly}
        onAdd={async (data) => {
          await api.addCoachAssignment(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteCoachAssignment(fighterId, id);
          refresh();
        }}
      />

      {/* TITLES */}
      <TitlesSection
        items={titles}
        readOnly={readOnly}
        onAdd={async (data) => {
          await api.addTitle(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteTitle(fighterId, id);
          refresh();
        }}
      />

      {/* SPONSORS */}
      <SponsorsSection
        items={sponsors}
        readOnly={readOnly}
        onAdd={async (data) => {
          await api.addSponsor(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteSponsor(fighterId, id);
          refresh();
        }}
      />
    </div>
  );
}

/* ---------- Coaches section ---------- */

function CoachesSection({
  fighter,
  coaches,
  allCoaches,
  readOnly,
  onAdd,
  onDelete,
}: {
  fighter: Fighter;
  coaches: CoachAssignment[];
  allCoaches: Coach[];
  readOnly?: boolean;
  onAdd: (data: {
    coach_id: string;
    role?: CoachRole;
    started_on?: string;
    ended_on?: string;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [coachId, setCoachId] = useState("");
  const [role, setRole] = useState<CoachRole>("head_coach");
  const [startedOn, setStartedOn] = useState("");

  const submit = async () => {
    if (!coachId) return;
    await onAdd({
      coach_id: coachId,
      role,
      started_on: startedOn || undefined,
    });
    setCoachId("");
    setRole("head_coach");
    setStartedOn("");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Gym &amp; coaches</h2>
        {!readOnly && (
          <button
            onClick={() => setAdding(!adding)}
            className="text-xs text-emerald-400 hover:underline"
          >
            {adding ? "cancel" : "+ assign coach"}
          </button>
        )}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <Field label="Gym" value={fighter.gym} />
        <Field label="Trainer (free-text)" value={fighter.trainer} />
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <div>
            <label className="text-xs text-neutral-400">Coach</label>
            <select
              value={coachId}
              onChange={(e) => setCoachId(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
            >
              <option value="">— pick a coach —</option>
              {allCoaches.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.gym ? ` (${c.gym})` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-neutral-400">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as CoachRole)}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
            >
              {(Object.keys(ROLE_LABELS) as CoachRole[]).map((k) => (
                <option key={k} value={k}>
                  {ROLE_LABELS[k]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-neutral-400">Started on</label>
            <input
              type="date"
              value={startedOn}
              onChange={(e) => setStartedOn(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
            />
          </div>
          <button
            onClick={submit}
            disabled={!coachId}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add assignment
          </button>
        </div>
      )}

      {coaches.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">
          No coach assignments yet. Coaches must exist as profiles on the
          roster first; assign them here so the bond shows up on both sides.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {coaches.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <Link href={`/coaches/${a.coach_id}`}>
                <ProfileAvatar
                  name={a.coach_name}
                  photo_path={a.coach_photo_path}
                  size={40}
                />
              </Link>
              <div className="flex-1">
                <div className="flex items-baseline gap-2">
                  <Link
                    href={`/coaches/${a.coach_id}`}
                    className="font-medium hover:underline"
                  >
                    {a.coach_name}
                  </Link>
                  <span className="pill bg-violet-500/15 text-violet-300">
                    {ROLE_LABELS[a.role]}
                  </span>
                  {!a.ended_on && (
                    <span className="pill bg-emerald-500/15 text-emerald-300">
                      current
                    </span>
                  )}
                </div>
                <div className="text-xs text-neutral-500">
                  {a.started_on
                    ? `since ${new Date(a.started_on).toLocaleDateString()}`
                    : "no start date"}
                  {a.ended_on
                    ? ` · until ${new Date(a.ended_on).toLocaleDateString()}`
                    : ""}
                </div>
              </div>
              {!readOnly && (
                <button
                  onClick={() => onDelete(a.id)}
                  className="text-xs text-neutral-500 hover:text-red-400"
                >
                  remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------- Titles section ---------- */

function TitlesSection({
  items,
  readOnly,
  onAdd,
  onDelete,
}: {
  items: FighterTitle[];
  readOnly?: boolean;
  onAdd: (data: {
    name: string;
    organization?: string;
    weight_class?: string;
    won_on?: string;
    lost_on?: string;
    status?: TitleStatus;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [organization, setOrganization] = useState("");
  const [weightClass, setWeightClass] = useState("");
  const [wonOn, setWonOn] = useState("");
  const [status, setStatus] = useState<TitleStatus>("active");

  const submit = async () => {
    if (!name.trim()) return;
    await onAdd({
      name: name.trim(),
      organization: organization.trim() || undefined,
      weight_class: weightClass.trim() || undefined,
      won_on: wonOn || undefined,
      status,
    });
    setName("");
    setOrganization("");
    setWeightClass("");
    setWonOn("");
    setStatus("active");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Titles</h2>
        {!readOnly && (
          <button
            onClick={() => setAdding(!adding)}
            className="text-xs text-emerald-400 hover:underline"
          >
            {adding ? "cancel" : "+ add title"}
          </button>
        )}
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <Input
            label="Title name *"
            value={name}
            onChange={setName}
            placeholder="WBC heavyweight"
          />
          <Input
            label="Organization"
            value={organization}
            onChange={setOrganization}
            placeholder="WBC / WBA / IBF / WBO"
          />
          <Input
            label="Weight class"
            value={weightClass}
            onChange={setWeightClass}
          />
          <Input
            label="Won on"
            type="date"
            value={wonOn}
            onChange={setWonOn}
          />
          <Select
            label="Status"
            value={status}
            onChange={(v) => setStatus(v as TitleStatus)}
            options={["active", "lost", "vacated", "retired"]}
          />
          <button
            onClick={submit}
            disabled={!name.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add title
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">No titles recorded.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((t) => (
            <li
              key={t.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span className={`pill ${STATUS_TINT[t.status]}`}>
                {t.status}
              </span>
              <div className="flex-1">
                <div className="font-medium">
                  {t.name}
                  {t.organization && (
                    <span className="ml-2 text-xs text-neutral-500">
                      {t.organization}
                    </span>
                  )}
                </div>
                <div className="text-xs text-neutral-500">
                  {[
                    t.weight_class,
                    t.won_on
                      ? `won ${new Date(t.won_on).toLocaleDateString()}`
                      : null,
                    t.lost_on
                      ? `lost ${new Date(t.lost_on).toLocaleDateString()}`
                      : null,
                    t.notes,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </div>
              </div>
              {!readOnly && (
                <button
                  onClick={() => onDelete(t.id)}
                  className="text-xs text-neutral-500 hover:text-red-400"
                >
                  remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------- Sponsors section ---------- */

function SponsorsSection({
  items,
  readOnly,
  onAdd,
  onDelete,
}: {
  items: FighterSponsor[];
  readOnly?: boolean;
  onAdd: (data: {
    name: string;
    started_on?: string;
    ended_on?: string;
    website?: string;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [startedOn, setStartedOn] = useState("");
  const [endedOn, setEndedOn] = useState("");

  const submit = async () => {
    if (!name.trim()) return;
    await onAdd({
      name: name.trim(),
      website: website.trim() || undefined,
      started_on: startedOn || undefined,
      ended_on: endedOn || undefined,
    });
    setName("");
    setWebsite("");
    setStartedOn("");
    setEndedOn("");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Sponsors</h2>
        {!readOnly && (
          <button
            onClick={() => setAdding(!adding)}
            className="text-xs text-emerald-400 hover:underline"
          >
            {adding ? "cancel" : "+ add sponsor"}
          </button>
        )}
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <Input label="Sponsor name *" value={name} onChange={setName} />
          <Input
            label="Website"
            value={website}
            onChange={setWebsite}
            placeholder="https://…"
          />
          <Input label="Started on" type="date" value={startedOn} onChange={setStartedOn} />
          <Input label="Ended on (blank = current)" type="date" value={endedOn} onChange={setEndedOn} />
          <button
            onClick={submit}
            disabled={!name.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add sponsor
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">No sponsors recorded.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((s) => (
            <li
              key={s.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span
                className={`pill ${
                  s.ended_on
                    ? "bg-neutral-700/40 text-neutral-300"
                    : "bg-emerald-500/15 text-emerald-300"
                }`}
              >
                {s.ended_on ? "past" : "current"}
              </span>
              <div className="flex-1">
                <div className="font-medium">
                  {s.website ? (
                    <a
                      href={s.website}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      {s.name}
                    </a>
                  ) : (
                    s.name
                  )}
                </div>
                <div className="text-xs text-neutral-500">
                  {[
                    s.started_on
                      ? `since ${new Date(s.started_on).toLocaleDateString()}`
                      : null,
                    s.ended_on
                      ? `until ${new Date(s.ended_on).toLocaleDateString()}`
                      : null,
                    s.notes,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </div>
              </div>
              {!readOnly && (
                <button
                  onClick={() => onDelete(s.id)}
                  className="text-xs text-neutral-500 hover:text-red-400"
                >
                  remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------- shared bits ---------- */

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-0.5 text-sm">{value ?? "—"}</div>
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
  options: string[];
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
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
