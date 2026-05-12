"use client";

import { useEffect, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type CoachingLevel,
  type Fighter,
  type FighterPatch,
  type Gym,
  type GymManager,
  type Hand,
  type Referee,
  type RefereeCertLevel,
  type SkillLevel,
  type Stance,
} from "@/lib/api";

type Kind = "fighter" | "coach" | "referee" | "gym" | "gym_manager";

interface Props {
  kind: Kind;
  /** When a gym manager creates a fighter/coach, auto-assign this gym. */
  gymId?: string;
  /** Coaches available for assignment (pre-filtered to same gym). */
  gymCoaches?: { id: string; name: string }[];
  onClose: () => void;
  onCreated: (id: string, name: string, photo_path: string | null) => void;
}

const TITLE: Record<Kind, string> = {
  fighter: "Create fighter profile",
  coach: "Create coach profile",
  referee: "Create referee profile",
  gym: "Create gym",
  gym_manager: "Create gym manager",
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
  dob: string;
  nationality: string;
  sex: "" | "male" | "female" | "other";
  email: string;
  phone: string;
  gym: string;
  specialties: string;
  coaching_level: "" | CoachingLevel;
  years_experience: string;
  certifications: string;
  license_number: string;
  license_expiry: string;
  languages: string;
  notable_fighters: string;
  bio: string;
}

interface RefereeForm {
  name: string;
  dob: string;
  nationality: string;
  sex: "" | "male" | "female" | "other";
  email: string;
  phone: string;
  license_number: string;
  sanctioning_body: string;
  certification_level: "" | RefereeCertLevel;
  license_expiry: string;
  years_officiating: string;
  languages: string;
  notable_bouts: string;
  bio: string;
}

interface GymForm {
  name: string;
  address: string;
  city: string;
  country: string;
  phone: string;
  email: string;
  specialties: string;
}

interface GymManagerForm {
  name: string;
  email: string;
  phone: string;
  gym_id: string;
}

export function CreateProfileModal({ kind, gymId, gymCoaches, onClose, onCreated }: Props) {
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [assignedCoachId, setAssignedCoachId] = useState("");

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
    dob: "",
    nationality: "",
    sex: "",
    email: "",
    phone: "",
    gym: "",
    specialties: "",
    coaching_level: "",
    years_experience: "",
    certifications: "",
    license_number: "",
    license_expiry: "",
    languages: "",
    notable_fighters: "",
    bio: "",
  });

  const [referee, setReferee] = useState<RefereeForm>({
    name: "",
    dob: "",
    nationality: "",
    sex: "",
    email: "",
    phone: "",
    license_number: "",
    sanctioning_body: "",
    certification_level: "",
    license_expiry: "",
    years_officiating: "",
    languages: "",
    notable_bouts: "",
    bio: "",
  });

  const [gym, setGym] = useState<GymForm>({
    name: "",
    address: "",
    city: "",
    country: "",
    phone: "",
    email: "",
    specialties: "",
  });

  const [gymMgr, setGymMgr] = useState<GymManagerForm>({
    name: "",
    email: "",
    phone: "",
    gym_id: "",
  });

  // Fetch gym list for the gym_manager form's dropdown
  const [gymList, setGymList] = useState<Gym[]>([]);
  useEffect(() => {
    if (kind === "gym_manager") {
      api.listGyms().then(setGymList).catch(() => {});
    }
  }, [kind]);

  const currentName =
    kind === "fighter"
      ? fighter.name
      : kind === "coach"
        ? coach.name
        : kind === "referee"
          ? referee.name
          : kind === "gym"
            ? gym.name
            : gymMgr.name;

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
          gymId,
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
        // Auto-assign coach if selected (gym manager flow)
        if (assignedCoachId) {
          try {
            await api.addCoachAssignment(id, { coach_id: assignedCoachId });
          } catch {
            // non-fatal — fighter was created, assignment can be done later
          }
        }
      } else if (kind === "coach") {
        const c: Coach = await api.createCoach({
          name: coach.name.trim(),
          gym: coach.gym.trim() || undefined,
          ...(gymId ? { gym_id: gymId } : {}),
        });
        id = c.id;
        const patch: Partial<Coach> = {};
        if (coach.dob) patch.dob = coach.dob;
        if (coach.nationality.trim()) patch.nationality = coach.nationality.trim();
        if (coach.sex) patch.sex = coach.sex;
        if (coach.email.trim()) patch.email = coach.email.trim();
        if (coach.phone.trim()) patch.phone = coach.phone.trim();
        if (coach.specialties.trim())
          patch.specialties = coach.specialties.trim();
        if (coach.coaching_level) patch.coaching_level = coach.coaching_level;
        const yrs = numOrNull(coach.years_experience);
        if (yrs != null) patch.years_experience = yrs;
        if (coach.certifications.trim())
          patch.certifications = coach.certifications.trim();
        if (coach.license_number.trim())
          patch.license_number = coach.license_number.trim();
        if (coach.license_expiry) patch.license_expiry = coach.license_expiry;
        if (coach.languages.trim()) patch.languages = coach.languages.trim();
        if (coach.notable_fighters.trim())
          patch.notable_fighters = coach.notable_fighters.trim();
        if (coach.bio.trim()) patch.bio = coach.bio.trim();
        if (Object.keys(patch).length > 0) {
          await api.updateCoach(id, patch);
        }
        if (photo) {
          const updated = await api.uploadCoachPhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else if (kind === "referee") {
        const r: Referee = await api.createReferee({
          name: referee.name.trim(),
          sanctioning_body: referee.sanctioning_body.trim() || undefined,
        });
        id = r.id;
        const patch: Partial<Referee> = {};
        if (referee.dob) patch.dob = referee.dob;
        if (referee.nationality.trim())
          patch.nationality = referee.nationality.trim();
        if (referee.sex) patch.sex = referee.sex;
        if (referee.email.trim()) patch.email = referee.email.trim();
        if (referee.phone.trim()) patch.phone = referee.phone.trim();
        if (referee.license_number.trim())
          patch.license_number = referee.license_number.trim();
        if (referee.certification_level)
          patch.certification_level = referee.certification_level;
        if (referee.license_expiry)
          patch.license_expiry = referee.license_expiry;
        const yo = numOrNull(referee.years_officiating);
        if (yo != null) patch.years_officiating = yo;
        if (referee.languages.trim()) patch.languages = referee.languages.trim();
        if (referee.notable_bouts.trim())
          patch.notable_bouts = referee.notable_bouts.trim();
        if (referee.bio.trim()) patch.bio = referee.bio.trim();
        if (Object.keys(patch).length > 0) {
          await api.updateReferee(id, patch);
        }
        if (photo) {
          const updated = await api.uploadRefereePhoto(id, photo);
          photo_path = updated.photo_path;
        }
      } else if (kind === "gym") {
        const data: Record<string, string> = { name: gym.name.trim() };
        if (gym.address.trim()) data.address = gym.address.trim();
        if (gym.city.trim()) data.city = gym.city.trim();
        if (gym.country.trim()) data.country = gym.country.trim();
        if (gym.phone.trim()) data.phone = gym.phone.trim();
        if (gym.email.trim()) data.email = gym.email.trim();
        if (gym.specialties.trim()) data.specialties = gym.specialties.trim();
        const g: Gym = await api.createGym(data as Parameters<typeof api.createGym>[0]);
        id = g.id;
        photo_path = null;
      } else {
        // gym_manager
        if (!gymMgr.gym_id) {
          setErr("Please select a gym.");
          setBusy(false);
          return;
        }
        const mgr: GymManager = await api.createGymManager({
          name: gymMgr.name.trim(),
          gym_id: gymMgr.gym_id,
          email: gymMgr.email.trim() || undefined,
          phone: gymMgr.phone.trim() || undefined,
        });
        id = mgr.id;
        photo_path = null;
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

          {kind !== "gym" && kind !== "gym_manager" && <div className="flex items-start gap-4">
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
          </div>}

          <Section title={kind === "gym" ? "Gym" : "Identity"}>
            <Input
              label={kind === "gym" ? "Gym name *" : "Full name *"}
              value={currentName}
              onChange={(v) => {
                if (kind === "fighter") setFighter({ ...fighter, name: v });
                else if (kind === "coach") setCoach({ ...coach, name: v });
                else if (kind === "referee") setReferee({ ...referee, name: v });
                else if (kind === "gym") setGym({ ...gym, name: v });
                else setGymMgr({ ...gymMgr, name: v });
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
                {gymCoaches && gymCoaches.length > 0 && (
                  <Select
                    label="Assigned Coach"
                    value={assignedCoachId}
                    onChange={(v) => setAssignedCoachId(v)}
                    options={[
                      { value: "", label: "— none —" },
                      ...gymCoaches.map((c) => ({
                        value: c.id,
                        label: c.name,
                      })),
                    ]}
                  />
                )}
              </Section>
            </>
          )}

          {kind === "coach" && (
            <>
              <Section title="Identity">
                <Input
                  label="Date of birth"
                  type="date"
                  value={coach.dob}
                  onChange={(v) => setCoach({ ...coach, dob: v })}
                />
                <Input
                  label="Nationality"
                  value={coach.nationality}
                  onChange={(v) => setCoach({ ...coach, nationality: v })}
                />
                <Select
                  label="Sex"
                  value={coach.sex}
                  onChange={(v) =>
                    setCoach({ ...coach, sex: v as CoachForm["sex"] })
                  }
                  options={[
                    { value: "", label: "—" },
                    { value: "male", label: "male" },
                    { value: "female", label: "female" },
                    { value: "other", label: "other" },
                  ]}
                />
              </Section>
              <Section title="Contact">
                <Input
                  label="Email"
                  type="email"
                  value={coach.email}
                  onChange={(v) => setCoach({ ...coach, email: v })}
                />
                <Input
                  label="Phone"
                  value={coach.phone}
                  onChange={(v) => setCoach({ ...coach, phone: v })}
                />
              </Section>
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
                <Select
                  label="Coaching level"
                  value={coach.coaching_level}
                  onChange={(v) =>
                    setCoach({
                      ...coach,
                      coaching_level: v as CoachForm["coaching_level"],
                    })
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
                  value={coach.years_experience}
                  onChange={(v) =>
                    setCoach({ ...coach, years_experience: v })
                  }
                />
              </Section>
              <Section title="Credentials">
                <Input
                  label="Certifications"
                  value={coach.certifications}
                  onChange={(v) => setCoach({ ...coach, certifications: v })}
                  placeholder="USA Boxing Level 2, AIBA 1-Star"
                />
                <Input
                  label="License number"
                  value={coach.license_number}
                  onChange={(v) => setCoach({ ...coach, license_number: v })}
                />
                <Input
                  label="License expiry"
                  type="date"
                  value={coach.license_expiry}
                  onChange={(v) => setCoach({ ...coach, license_expiry: v })}
                />
                <Input
                  label="Languages"
                  value={coach.languages}
                  onChange={(v) => setCoach({ ...coach, languages: v })}
                  placeholder="English, Spanish"
                />
              </Section>
              <Section title="Track record">
                <Textarea
                  label="Notable fighters trained"
                  value={coach.notable_fighters}
                  onChange={(v) =>
                    setCoach({ ...coach, notable_fighters: v })
                  }
                  rows={2}
                />
                <Textarea
                  label="Bio"
                  value={coach.bio}
                  onChange={(v) => setCoach({ ...coach, bio: v })}
                  rows={4}
                />
              </Section>
            </>
          )}

          {kind === "gym" && (
            <>
              <Section title="Details">
                <Input
                  label="Address"
                  value={gym.address}
                  onChange={(v) => setGym({ ...gym, address: v })}
                  placeholder="123 Main St"
                />
                <Input
                  label="City"
                  value={gym.city}
                  onChange={(v) => setGym({ ...gym, city: v })}
                />
                <Input
                  label="Country"
                  value={gym.country}
                  onChange={(v) => setGym({ ...gym, country: v })}
                />
              </Section>
              <Section title="Contact">
                <Input
                  label="Phone"
                  value={gym.phone}
                  onChange={(v) => setGym({ ...gym, phone: v })}
                />
                <Input
                  label="Email"
                  type="email"
                  value={gym.email}
                  onChange={(v) => setGym({ ...gym, email: v })}
                />
              </Section>
              <Section title="Info">
                <Input
                  label="Specialties"
                  value={gym.specialties}
                  onChange={(v) => setGym({ ...gym, specialties: v })}
                  placeholder="boxing, MMA, kickboxing"
                />
              </Section>
            </>
          )}

          {kind === "gym_manager" && (
            <>
              <Section title="Assigned Gym">
                <Select
                  label="Gym *"
                  value={gymMgr.gym_id}
                  onChange={(v) => setGymMgr({ ...gymMgr, gym_id: v })}
                  options={[
                    { value: "", label: "— select a gym —" },
                    ...gymList.map((g) => ({
                      value: g.id,
                      label: g.name,
                    })),
                  ]}
                />
              </Section>
              <Section title="Contact">
                <Input
                  label="Email"
                  type="email"
                  value={gymMgr.email}
                  onChange={(v) => setGymMgr({ ...gymMgr, email: v })}
                />
                <Input
                  label="Phone"
                  value={gymMgr.phone}
                  onChange={(v) => setGymMgr({ ...gymMgr, phone: v })}
                />
              </Section>
            </>
          )}

          {kind === "referee" && (
            <>
              <Section title="Identity">
                <Input
                  label="Date of birth"
                  type="date"
                  value={referee.dob}
                  onChange={(v) => setReferee({ ...referee, dob: v })}
                />
                <Input
                  label="Nationality"
                  value={referee.nationality}
                  onChange={(v) => setReferee({ ...referee, nationality: v })}
                />
                <Select
                  label="Sex"
                  value={referee.sex}
                  onChange={(v) =>
                    setReferee({ ...referee, sex: v as RefereeForm["sex"] })
                  }
                  options={[
                    { value: "", label: "—" },
                    { value: "male", label: "male" },
                    { value: "female", label: "female" },
                    { value: "other", label: "other" },
                  ]}
                />
              </Section>
              <Section title="Contact">
                <Input
                  label="Email"
                  type="email"
                  value={referee.email}
                  onChange={(v) => setReferee({ ...referee, email: v })}
                />
                <Input
                  label="Phone"
                  value={referee.phone}
                  onChange={(v) => setReferee({ ...referee, phone: v })}
                />
              </Section>
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
                <Select
                  label="Certification level"
                  value={referee.certification_level}
                  onChange={(v) =>
                    setReferee({
                      ...referee,
                      certification_level:
                        v as RefereeForm["certification_level"],
                    })
                  }
                  options={[
                    { value: "", label: "—" },
                    { value: "local", label: "local" },
                    { value: "regional", label: "regional" },
                    { value: "national", label: "national" },
                    { value: "international", label: "international" },
                  ]}
                />
                <Input
                  label="License expiry"
                  type="date"
                  value={referee.license_expiry}
                  onChange={(v) =>
                    setReferee({ ...referee, license_expiry: v })
                  }
                />
                <Input
                  label="Years officiating"
                  type="number"
                  value={referee.years_officiating}
                  onChange={(v) =>
                    setReferee({ ...referee, years_officiating: v })
                  }
                />
                <Input
                  label="Languages"
                  value={referee.languages}
                  onChange={(v) => setReferee({ ...referee, languages: v })}
                  placeholder="English, Spanish"
                />
              </Section>
              <Section title="Track record">
                <Textarea
                  label="Notable bouts officiated"
                  value={referee.notable_bouts}
                  onChange={(v) =>
                    setReferee({ ...referee, notable_bouts: v })
                  }
                  rows={2}
                />
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
