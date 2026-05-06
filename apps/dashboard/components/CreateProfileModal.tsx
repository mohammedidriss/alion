"use client";

import { useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type Fighter,
  type FighterPatch,
  type Hand,
  type Referee,
  type SkillLevel,
  type Stance,
} from "@/lib/api";

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

const SKILL_LEVELS: SkillLevel[] = [
  "recreational",
  "amateur_novice",
  "amateur_open",
  "amateur_elite",
  "semi_pro",
  "professional",
  "coach",
];

const WEIGHT_CLASSES = [
  "minimumweight",
  "light_flyweight",
  "flyweight",
  "super_flyweight",
  "bantamweight",
  "super_bantamweight",
  "featherweight",
  "super_featherweight",
  "lightweight",
  "super_lightweight",
  "welterweight",
  "super_welterweight",
  "middleweight",
  "super_middleweight",
  "light_heavyweight",
  "cruiserweight",
  "heavyweight",
];

interface FighterForm {
  name: string;
  nickname: string;
  dob: string;
  nationality: string;
  sex: "" | "male" | "female" | "other";
  stance: Stance;
  dominant_hand: "" | Hand;
  height_cm: string;
  reach_cm: string;
  weight_kg: string;
  weight_class: string;
  skill_level: "" | SkillLevel;
  years_training: string;
  gym: string;
  trainer: string;
}

interface CoachForm {
  name: string;
  gym: string;
  specialties: string;
  years_experience: string;
  bio: string;
}

interface RefereeForm {
  name: string;
  license_number: string;
  sanctioning_body: string;
  license_expiry: string;
  bio: string;
}

export function CreateProfileModal({ kind, onClose, onCreated }: Props) {
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [fighter, setFighter] = useState<FighterForm>({
    name: "",
    nickname: "",
    dob: "",
    nationality: "",
    sex: "",
    stance: "orthodox",
    dominant_hand: "",
    height_cm: "",
    reach_cm: "",
    weight_kg: "",
    weight_class: "",
    skill_level: "",
    years_training: "",
    gym: "",
    trainer: "",
  });

  const [coach, setCoach] = useState<CoachForm>({
    name: "",
    gym: "",
    specialties: "",
    years_experience: "",
    bio: "",
  });

  const [referee, setReferee] = useState<RefereeForm>({
    name: "",
    license_number: "",
    sanctioning_body: "",
    license_expiry: "",
    bio: "",
  });

  const currentName =
    kind === "fighter" ? fighter.name : kind === "coach" ? coach.name : referee.name;

  const onPick = (f: File | null) => {
    setPhoto(f);
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhotoPreview(f ? URL.createObjectURL(f) : null);
  };

  const numOrNull = (s: string): number | null => {
    if (!s.trim()) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  };

  const submit = async () => {
    if (!currentName.trim()) {
      setErr("Name is required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      let id: string;
      let photo_path: string | null = null;

      if (kind === "fighter") {
        const f: Fighter = await api.createFighter(
          fighter.name.trim(),
          fighter.stance,
        );
        id = f.id;
        const patch: FighterPatch = {};
        if (fighter.nickname.trim()) patch.nickname = fighter.nickname.trim();
        if (fighter.dob) patch.dob = fighter.dob;
        if (fighter.nationality.trim())
          patch.nationality = fighter.nationality.trim();
        if (fighter.sex) patch.sex = fighter.sex;
        if (fighter.dominant_hand) patch.dominant_hand = fighter.dominant_hand;
        const hc = numOrNull(fighter.height_cm);
        if (hc != null) patch.height_cm = hc;
        const rc = numOrNull(fighter.reach_cm);
        if (rc != null) patch.reach_cm = rc;
        const wk = numOrNull(fighter.weight_kg);
        if (wk != null) patch.weight_kg = wk;
        if (fighter.weight_class) patch.weight_class = fighter.weight_class;
        if (fighter.skill_level) patch.skill_level = fighter.skill_level;
        const yt = numOrNull(fighter.years_training);
        if (yt != null) patch.years_training = yt;
        if (fighter.gym.trim()) patch.gym = fighter.gym.trim();
        if (fighter.trainer.trim()) patch.trainer = fighter.trainer.trim();
        if (Object.keys(patch).length > 0) {
          await api.updateFighter(id, patch);
        }
        if (photo) {
          const updated = await api.uploadFighterPhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else if (kind === "coach") {
        const c: Coach = await api.createCoach({
          name: coach.name.trim(),
          gym: coach.gym.trim() || undefined,
        });
        id = c.id;
        const yrs = numOrNull(coach.years_experience);
        const patch: Partial<Coach> = {};
        if (coach.specialties.trim())
          patch.specialties = coach.specialties.trim();
        if (yrs != null) patch.years_experience = yrs;
        if (coach.bio.trim()) patch.bio = coach.bio.trim();
        if (Object.keys(patch).length > 0) {
          await api.updateCoach(id, patch);
        }
        if (photo) {
          const updated = await api.uploadCoachPhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else {
        const r: Referee = await api.createReferee({
          name: referee.name.trim(),
          sanctioning_body: referee.sanctioning_body.trim() || undefined,
        });
        id = r.id;
        const patch: Partial<Referee> = {};
        if (referee.license_number.trim())
          patch.license_number = referee.license_number.trim();
        if (referee.license_expiry)
          patch.license_expiry = referee.license_expiry;
        if (referee.bio.trim()) patch.bio = referee.bio.trim();
        if (Object.keys(patch).length > 0) {
          await api.updateReferee(id, patch);
        }
        if (photo) {
          const updated = await api.uploadRefereePhoto(id, photo);
          photo_path = updated.photo_path;
        }
      }
      onCreated(id, currentName.trim(), photo_path);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-white/5 bg-[#13131a] shadow-xl">
        <header className="flex items-center justify-between border-b border-white/5 p-5">
          <h3 className="text-lg font-semibold">{TITLE[kind]}</h3>
          <button
            onClick={onClose}
            disabled={busy}
            className="text-sm text-neutral-400 hover:text-neutral-100"
          >
            ✕
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {err && (
            <p className="mb-4 rounded-xl border border-red-500/30 bg-red-950/30 p-2 text-sm text-red-200">
              {err}
            </p>
          )}

          <div className="flex items-start gap-4">
            {photoPreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={photoPreview}
                alt="preview"
                className="h-24 w-24 shrink-0 rounded-full object-cover"
              />
            ) : (
              <ProfileAvatar
                name={currentName || "?"}
                photo_path={null}
                size={96}
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

          <Section title="Identity">
            <Input
              label="Full name *"
              value={currentName}
              onChange={(v) => {
                if (kind === "fighter") setFighter({ ...fighter, name: v });
                else if (kind === "coach") setCoach({ ...coach, name: v });
                else setReferee({ ...referee, name: v });
              }}
              autoFocus
            />
            {kind === "fighter" && (
              <>
                <Input
                  label="Nickname"
                  value={fighter.nickname}
                  onChange={(v) => setFighter({ ...fighter, nickname: v })}
                  placeholder="e.g. The Hammer"
                />
                <Input
                  label="Date of birth"
                  type="date"
                  value={fighter.dob}
                  onChange={(v) => setFighter({ ...fighter, dob: v })}
                />
                <Input
                  label="Nationality"
                  value={fighter.nationality}
                  onChange={(v) => setFighter({ ...fighter, nationality: v })}
                />
                <Select
                  label="Sex"
                  value={fighter.sex}
                  onChange={(v) =>
                    setFighter({ ...fighter, sex: v as FighterForm["sex"] })
                  }
                  options={[
                    { value: "", label: "—" },
                    { value: "male", label: "male" },
                    { value: "female", label: "female" },
                    { value: "other", label: "other" },
                  ]}
                />
              </>
            )}
          </Section>

          {kind === "fighter" && (
            <>
              <Section title="Boxing">
                <Select
                  label="Stance"
                  value={fighter.stance}
                  onChange={(v) =>
                    setFighter({ ...fighter, stance: v as Stance })
                  }
                  options={[
                    { value: "orthodox", label: "orthodox" },
                    { value: "southpaw", label: "southpaw" },
                    { value: "switch", label: "switch" },
                  ]}
                />
                <Select
                  label="Dominant hand"
                  value={fighter.dominant_hand}
                  onChange={(v) =>
                    setFighter({
                      ...fighter,
                      dominant_hand: v as FighterForm["dominant_hand"],
                    })
                  }
                  options={[
                    { value: "", label: "—" },
                    { value: "left", label: "left" },
                    { value: "right", label: "right" },
                  ]}
                />
                <Select
                  label="Skill level"
                  value={fighter.skill_level}
                  onChange={(v) =>
                    setFighter({
                      ...fighter,
                      skill_level: v as FighterForm["skill_level"],
                    })
                  }
                  options={[
                    { value: "", label: "—" },
                    ...SKILL_LEVELS.map((s) => ({
                      value: s,
                      label: s.replace(/_/g, " "),
                    })),
                  ]}
                />
                <Select
                  label="Weight class"
                  value={fighter.weight_class}
                  onChange={(v) =>
                    setFighter({ ...fighter, weight_class: v })
                  }
                  options={[
                    { value: "", label: "—" },
                    ...WEIGHT_CLASSES.map((w) => ({
                      value: w,
                      label: w.replace(/_/g, " "),
                    })),
                  ]}
                />
                <Input
                  label="Years training"
                  type="number"
                  value={fighter.years_training}
                  onChange={(v) =>
                    setFighter({ ...fighter, years_training: v })
                  }
                />
              </Section>

              <Section title="Physical">
                <Input
                  label="Height (cm)"
                  type="number"
                  value={fighter.height_cm}
                  onChange={(v) => setFighter({ ...fighter, height_cm: v })}
                />
                <Input
                  label="Reach (cm)"
                  type="number"
                  value={fighter.reach_cm}
                  onChange={(v) => setFighter({ ...fighter, reach_cm: v })}
                />
                <Input
                  label="Weight (kg)"
                  type="number"
                  value={fighter.weight_kg}
                  onChange={(v) => setFighter({ ...fighter, weight_kg: v })}
                />
              </Section>

              <Section title="Affiliation">
                <Input
                  label="Gym"
                  value={fighter.gym}
                  onChange={(v) => setFighter({ ...fighter, gym: v })}
                />
                <Input
                  label="Trainer"
                  value={fighter.trainer}
                  onChange={(v) => setFighter({ ...fighter, trainer: v })}
                />
              </Section>
            </>
          )}

          {kind === "coach" && (
            <>
              <Section title="Coaching">
                <Input
                  label="Gym"
                  value={coach.gym}
                  onChange={(v) => setCoach({ ...coach, gym: v })}
                  placeholder="e.g. Iron Gym"
                />
                <Input
                  label="Specialties"
                  value={coach.specialties}
                  onChange={(v) => setCoach({ ...coach, specialties: v })}
                  placeholder="head movement, defense, conditioning"
                />
                <Input
                  label="Years experience"
                  type="number"
                  value={coach.years_experience}
                  onChange={(v) =>
                    setCoach({ ...coach, years_experience: v })
                  }
                />
              </Section>
              <Section title="Bio">
                <Textarea
                  label="Bio"
                  value={coach.bio}
                  onChange={(v) => setCoach({ ...coach, bio: v })}
                  rows={4}
                />
              </Section>
            </>
          )}

          {kind === "referee" && (
            <>
              <Section title="Credentials">
                <Input
                  label="Sanctioning body"
                  value={referee.sanctioning_body}
                  onChange={(v) =>
                    setReferee({ ...referee, sanctioning_body: v })
                  }
                  placeholder="e.g. USA Boxing"
                />
                <Input
                  label="License number"
                  value={referee.license_number}
                  onChange={(v) =>
                    setReferee({ ...referee, license_number: v })
                  }
                />
                <Input
                  label="License expiry"
                  type="date"
                  value={referee.license_expiry}
                  onChange={(v) =>
                    setReferee({ ...referee, license_expiry: v })
                  }
                />
              </Section>
              <Section title="Bio">
                <Textarea
                  label="Bio"
                  value={referee.bio}
                  onChange={(v) => setReferee({ ...referee, bio: v })}
                  rows={4}
                />
              </Section>
            </>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-white/5 p-4">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-xl bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || !currentName.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-1.5 text-sm font-medium text-black hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
          >
            {busy ? "Creating…" : "Create profile"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-5">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
        {title}
      </h4>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {children}
      </div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  autoFocus?: boolean;
}) {
  return (
    <div>
      <label className="text-xs text-neutral-400">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
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
