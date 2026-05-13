"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type CoachPatch,
  type CoachingLevel,
  type Fighter,
  type FighterPatch,
  type FighterTitle,
  type Hand,
  type SkillLevel,
  type Stance,
  type TitleStatus,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

// --- Constants ---
const STANCES: Stance[] = ["orthodox", "southpaw", "switch"];
const HANDS: Hand[] = ["left", "right"];
const SKILL_LEVELS: SkillLevel[] = [
  "recreational", "amateur_novice", "amateur_open", "amateur_elite",
  "semi_pro", "professional", "coach",
];
const SEXES = ["male", "female", "other"];
const WEIGHT_CLASSES = [
  "minimumweight", "light_flyweight", "flyweight", "super_flyweight",
  "bantamweight", "super_bantamweight", "featherweight", "super_featherweight",
  "lightweight", "super_lightweight", "welterweight", "super_welterweight",
  "middleweight", "super_middleweight", "light_heavyweight", "cruiserweight",
  "heavyweight",
];
const COACHING_LEVELS: CoachingLevel[] = ["amateur", "professional", "both"];

function label(s: string) {
  return s.replace(/_/g, " ");
}

// --- Styles ---
const inputCls =
  "w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none";
const labelCls = "mb-1 block text-xs font-medium text-neutral-400";
const selectCls =
  "w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none appearance-none";
const sectionCls = "rounded-xl border border-white/5 p-5 space-y-4";
const legendCls = "px-2 text-xs uppercase tracking-wider text-neutral-500";

export default function ProfilePage() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();

  // --- Account fields ---
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // --- Fighter fields ---
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [fNickname, setFNickname] = useState("");
  const [fDob, setFDob] = useState("");
  const [fSex, setFSex] = useState("");
  const [fNationality, setFNationality] = useState("");
  const [fStance, setFStance] = useState<Stance>("orthodox");
  const [fDominantHand, setFDominantHand] = useState("");
  const [fSkillLevel, setFSkillLevel] = useState("");
  const [fWeightClass, setFWeightClass] = useState("");
  const [fYearsTraining, setFYearsTraining] = useState("");
  const [fHeightCm, setFHeightCm] = useState("");
  const [fReachCm, setFReachCm] = useState("");
  const [fWeightKg, setFWeightKg] = useState("");
  const [fShoulderCm, setFShoulderCm] = useState("");
  const [fWins, setFWins] = useState("");
  const [fLosses, setFLosses] = useState("");
  const [fDraws, setFDraws] = useState("");
  const [fKos, setFKos] = useState("");
  const [fBoxrecId, setFBoxrecId] = useState("");
  const [fUsaBoxingId, setFUsaBoxingId] = useState("");
  const [fBio, setFBio] = useState("");
  const [fNotes, setFNotes] = useState("");

  // --- Titles ---
  const [titles, setTitles] = useState<FighterTitle[]>([]);
  const [showTitleForm, setShowTitleForm] = useState(false);
  const [tName, setTName] = useState("");
  const [tOrg, setTOrg] = useState("");
  const [tWeightClass, setTWeightClass] = useState("");
  const [tWonOn, setTWonOn] = useState("");
  const [tStatus, setTStatus] = useState<TitleStatus>("active");
  const [addingTitle, setAddingTitle] = useState(false);

  // --- Coach fields ---
  const [coach, setCoach] = useState<Coach | null>(null);
  const [cSpecialties, setCSpecialties] = useState("");
  const [cCoachingLevel, setCCoachingLevel] = useState("");
  const [cYearsExp, setCYearsExp] = useState("");
  const [cCertifications, setCCertifications] = useState("");
  const [cLicenseNumber, setCLicenseNumber] = useState("");
  const [cLicenseExpiry, setCLicenseExpiry] = useState("");
  const [cLanguages, setCLanguages] = useState("");
  const [cNotableFighters, setCNotableFighters] = useState("");
  const [cPhone, setCPhone] = useState("");
  const [cDob, setCDob] = useState("");
  const [cSex, setCSex] = useState("");
  const [cNationality, setCNationality] = useState("");
  const [cBio, setCBio] = useState("");
  const [cNotes, setCNotes] = useState("");

  // --- State ---
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);

  // Sync account fields when user changes
  useEffect(() => {
    if (user) {
      setName(user.name);
      setEmail(user.email);
    }
  }, [user]);

  // Load role-specific profile
  useEffect(() => {
    if (!user?.profile_id) return;
    setProfileLoading(true);

    if (user.role === "fighter") {
      Promise.all([
        api.getFighter(user.profile_id),
        api.listTitles(user.profile_id),
      ])
        .then(([f, t]) => {
          setFighter(f);
          setTitles(t);
          // Populate fields
          setFNickname(f.nickname ?? "");
          setFDob(f.dob ?? "");
          setFSex(f.sex ?? "");
          setFNationality(f.nationality ?? "");
          setFStance(f.stance ?? "orthodox");
          setFDominantHand(f.dominant_hand ?? "");
          setFSkillLevel(f.skill_level ?? "");
          setFWeightClass(f.weight_class ?? "");
          setFYearsTraining(f.years_training != null ? String(f.years_training) : "");
          setFHeightCm(f.height_cm != null ? String(f.height_cm) : "");
          setFReachCm(f.reach_cm != null ? String(f.reach_cm) : "");
          setFWeightKg(f.weight_kg != null ? String(f.weight_kg) : "");
          setFShoulderCm(f.shoulder_width_cm != null ? String(f.shoulder_width_cm) : "");
          setFWins(String(f.record_wins));
          setFLosses(String(f.record_losses));
          setFDraws(String(f.record_draws));
          setFKos(String(f.record_kos));
          setFBoxrecId(f.boxrec_id ?? "");
          setFUsaBoxingId(f.usa_boxing_id ?? "");
          setFBio(f.bio ?? "");
          setFNotes(f.notes ?? "");
        })
        .catch(() => {})
        .finally(() => setProfileLoading(false));
    } else if (user.role === "coach") {
      api
        .getCoach(user.profile_id)
        .then((c) => {
          setCoach(c);
          setCSpecialties(c.specialties ?? "");
          setCCoachingLevel(c.coaching_level ?? "");
          setCYearsExp(c.years_experience != null ? String(c.years_experience) : "");
          setCCertifications(c.certifications ?? "");
          setCLicenseNumber(c.license_number ?? "");
          setCLicenseExpiry(c.license_expiry ?? "");
          setCLanguages(c.languages ?? "");
          setCNotableFighters(c.notable_fighters ?? "");
          setCPhone(c.phone ?? "");
          setCDob(c.dob ?? "");
          setCSex(c.sex ?? "");
          setCNationality(c.nationality ?? "");
          setCBio(c.bio ?? "");
          setCNotes(c.notes ?? "");
        })
        .catch(() => {})
        .finally(() => setProfileLoading(false));
    } else {
      setProfileLoading(false);
    }
  }, [user?.profile_id, user?.role]);

  if (!user) {
    return (
      <div className="px-8 py-12 text-neutral-400">
        Please sign in to view your profile.
      </div>
    );
  }

  // --- Save handler ---
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    // 1) Account-level changes
    const accountPayload: {
      name?: string;
      email?: string;
      current_password?: string;
      new_password?: string;
    } = {};
    if (name.trim() !== user.name) accountPayload.name = name.trim();
    if (email.trim().toLowerCase() !== user.email)
      accountPayload.email = email.trim();

    if (newPassword) {
      if (newPassword !== confirmPassword) {
        setError("New passwords do not match.");
        return;
      }
      if (!currentPassword) {
        setError("Enter your current password to change it.");
        return;
      }
      accountPayload.current_password = currentPassword;
      accountPayload.new_password = newPassword;
    }

    // Build role-specific patch BEFORE saving so we can detect "no changes"
    let fighterPatch: FighterPatch = {};
    let coachPatch: CoachPatch = {};

    if (user.role === "fighter" && user.profile_id && fighter) {
      const s = (v: string) => v.trim() || null;
      const n = (v: string) => (v.trim() ? Number(v) : null);
      const ni = (v: string) => (v.trim() ? parseInt(v, 10) : null);

      if (fNickname !== (fighter.nickname ?? "")) fighterPatch.nickname = s(fNickname);
      if (fDob !== (fighter.dob ?? "")) fighterPatch.dob = s(fDob);
      if (fSex !== (fighter.sex ?? "")) fighterPatch.sex = s(fSex);
      if (fNationality !== (fighter.nationality ?? "")) fighterPatch.nationality = s(fNationality);
      if (fStance !== (fighter.stance ?? "orthodox")) fighterPatch.stance = fStance;
      if (fDominantHand !== (fighter.dominant_hand ?? "")) fighterPatch.dominant_hand = s(fDominantHand) as Hand | null;
      if (fSkillLevel !== (fighter.skill_level ?? "")) fighterPatch.skill_level = s(fSkillLevel) as SkillLevel | null;
      if (fWeightClass !== (fighter.weight_class ?? "")) fighterPatch.weight_class = s(fWeightClass);
      if (fYearsTraining !== (fighter.years_training != null ? String(fighter.years_training) : "")) fighterPatch.years_training = ni(fYearsTraining);
      if (fHeightCm !== (fighter.height_cm != null ? String(fighter.height_cm) : "")) fighterPatch.height_cm = n(fHeightCm);
      if (fReachCm !== (fighter.reach_cm != null ? String(fighter.reach_cm) : "")) fighterPatch.reach_cm = n(fReachCm);
      if (fWeightKg !== (fighter.weight_kg != null ? String(fighter.weight_kg) : "")) fighterPatch.weight_kg = n(fWeightKg);
      if (fShoulderCm !== (fighter.shoulder_width_cm != null ? String(fighter.shoulder_width_cm) : "")) fighterPatch.shoulder_width_cm = n(fShoulderCm);
      if (fWins !== String(fighter.record_wins ?? 0)) fighterPatch.record_wins = parseInt(fWins, 10) || 0;
      if (fLosses !== String(fighter.record_losses ?? 0)) fighterPatch.record_losses = parseInt(fLosses, 10) || 0;
      if (fDraws !== String(fighter.record_draws ?? 0)) fighterPatch.record_draws = parseInt(fDraws, 10) || 0;
      if (fKos !== String(fighter.record_kos ?? 0)) fighterPatch.record_kos = parseInt(fKos, 10) || 0;
      if (fBoxrecId !== (fighter.boxrec_id ?? "")) fighterPatch.boxrec_id = s(fBoxrecId);
      if (fUsaBoxingId !== (fighter.usa_boxing_id ?? "")) fighterPatch.usa_boxing_id = s(fUsaBoxingId);
      if (fBio !== (fighter.bio ?? "")) fighterPatch.bio = s(fBio);
      if (fNotes !== (fighter.notes ?? "")) fighterPatch.notes = s(fNotes);
    }

    if (user.role === "coach" && user.profile_id && coach) {
      const s = (v: string) => v.trim() || null;
      const ni = (v: string) => (v.trim() ? parseInt(v, 10) : null);

      if (cSpecialties !== (coach.specialties ?? "")) coachPatch.specialties = s(cSpecialties);
      if (cCoachingLevel !== (coach.coaching_level ?? "")) coachPatch.coaching_level = s(cCoachingLevel) as CoachingLevel | null;
      if (cYearsExp !== (coach.years_experience != null ? String(coach.years_experience) : "")) coachPatch.years_experience = ni(cYearsExp);
      if (cCertifications !== (coach.certifications ?? "")) coachPatch.certifications = s(cCertifications);
      if (cLicenseNumber !== (coach.license_number ?? "")) coachPatch.license_number = s(cLicenseNumber);
      if (cLicenseExpiry !== (coach.license_expiry ?? "")) coachPatch.license_expiry = s(cLicenseExpiry);
      if (cLanguages !== (coach.languages ?? "")) coachPatch.languages = s(cLanguages);
      if (cNotableFighters !== (coach.notable_fighters ?? "")) coachPatch.notable_fighters = s(cNotableFighters);
      if (cPhone !== (coach.phone ?? "")) coachPatch.phone = s(cPhone);
      if (cDob !== (coach.dob ?? "")) coachPatch.dob = s(cDob);
      if (cSex !== (coach.sex ?? "")) coachPatch.sex = s(cSex);
      if (cNationality !== (coach.nationality ?? "")) coachPatch.nationality = s(cNationality);
      if (cBio !== (coach.bio ?? "")) coachPatch.bio = s(cBio);
      if (cNotes !== (coach.notes ?? "")) coachPatch.notes = s(cNotes);
    }

    const hasAccountChanges = Object.keys(accountPayload).length > 0;
    const hasProfileChanges =
      Object.keys(fighterPatch).length > 0 || Object.keys(coachPatch).length > 0;

    if (!hasAccountChanges && !hasProfileChanges) {
      setSuccess("No changes to save.");
      return;
    }

    setSaving(true);
    try {
      if (hasAccountChanges) {
        await api.updateProfile(accountPayload);
      }

      if (Object.keys(fighterPatch).length > 0 && user.profile_id) {
        const updated = await api.updateFighter(user.profile_id, fighterPatch);
        setFighter(updated);
      }

      if (Object.keys(coachPatch).length > 0 && user.profile_id) {
        const updated = await api.updateCoach(user.profile_id, coachPatch);
        setCoach(updated);
      }

      setSuccess("Profile updated successfully.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      if (refreshUser) await refreshUser();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Update failed";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  // --- Add title handler ---
  const handleAddTitle = async () => {
    if (!tName.trim() || !user.profile_id) return;
    setAddingTitle(true);
    try {
      const t = await api.addTitle(user.profile_id, {
        name: tName.trim(),
        organization: tOrg.trim() || undefined,
        weight_class: tWeightClass || undefined,
        won_on: tWonOn || undefined,
        status: tStatus,
      });
      setTitles((prev) => [...prev, t]);
      setTName("");
      setTOrg("");
      setTWeightClass("");
      setTWonOn("");
      setTStatus("active");
      setShowTitleForm(false);
    } catch {
      setError("Failed to add title.");
    } finally {
      setAddingTitle(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-8 py-8">
      {/* Header */}
      <header className="flex items-center gap-4">
        <ProfileAvatar name={user.name} photo_path={user.photo_path} size={64} />
        <div>
          <h1 className="text-2xl font-bold">{user.name}</h1>
          <p className="text-sm text-neutral-500">
            {user.role === "gym_manager"
              ? "Gym Manager"
              : user.role.charAt(0).toUpperCase() + user.role.slice(1)}
            {user.profile_id && (
              <span className="ml-2 text-neutral-600">
                System ID:{" "}
                <code className="rounded bg-white/[0.05] px-1 py-0.5 font-mono text-[10px] text-neutral-500 select-all">
                  {user.profile_id}
                </code>
              </span>
            )}
          </p>
        </div>
      </header>

      {profileLoading && (
        <div className="text-sm text-neutral-500 animate-pulse">Loading profile data…</div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* ═══════════════════ ACCOUNT INFO ═══════════════════ */}
        <fieldset className={sectionCls}>
          <legend className={legendCls}>Account Information</legend>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className={labelCls}>Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="your@email.com" className={inputCls} />
            </div>
          </div>
        </fieldset>

        {/* ═══════════════════ CHANGE PASSWORD ═══════════════════ */}
        <fieldset className={sectionCls}>
          <legend className={legendCls}>Change Password</legend>
          <p className="text-xs text-neutral-500">Leave blank to keep your current password.</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className={labelCls}>Current Password</label>
              <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Current password" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>New Password</label>
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Min 6 characters" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Confirm New Password</label>
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Confirm new password" className={inputCls} />
            </div>
          </div>
        </fieldset>

        {/* ═══════════════════ FIGHTER SECTIONS ═══════════════════ */}
        {user.role === "fighter" && fighter && (
          <>
            {/* Identity */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Identity</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className={labelCls}>Nickname</label>
                  <input type="text" value={fNickname} onChange={(e) => setFNickname(e.target.value)} placeholder="Ring name" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Date of Birth</label>
                  <input type="date" value={fDob} onChange={(e) => setFDob(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Sex</label>
                  <select value={fSex} onChange={(e) => setFSex(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {SEXES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Nationality</label>
                  <input type="text" value={fNationality} onChange={(e) => setFNationality(e.target.value)} placeholder="e.g. Lebanese" className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Boxing */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Boxing</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className={labelCls}>Stance</label>
                  <select value={fStance} onChange={(e) => setFStance(e.target.value as Stance)} className={selectCls}>
                    {STANCES.map((s) => (
                      <option key={s} value={s}>{label(s)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Dominant Hand</label>
                  <select value={fDominantHand} onChange={(e) => setFDominantHand(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {HANDS.map((h) => (
                      <option key={h} value={h}>{h}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Skill Level</label>
                  <select value={fSkillLevel} onChange={(e) => setFSkillLevel(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {SKILL_LEVELS.map((l) => (
                      <option key={l} value={l}>{label(l)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Weight Class</label>
                  <select value={fWeightClass} onChange={(e) => setFWeightClass(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {WEIGHT_CLASSES.map((w) => (
                      <option key={w} value={w}>{label(w)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Years Training</label>
                  <input type="number" min={0} value={fYearsTraining} onChange={(e) => setFYearsTraining(e.target.value)} className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Physical */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Physical Measurements</legend>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <label className={labelCls}>Height (cm)</label>
                  <input type="number" step="0.1" value={fHeightCm} onChange={(e) => setFHeightCm(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Reach (cm)</label>
                  <input type="number" step="0.1" value={fReachCm} onChange={(e) => setFReachCm(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Weight (kg)</label>
                  <input type="number" step="0.1" value={fWeightKg} onChange={(e) => setFWeightKg(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Shoulder Width (cm)</label>
                  <input type="number" step="0.1" value={fShoulderCm} onChange={(e) => setFShoulderCm(e.target.value)} className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Record */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Fight Record</legend>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <label className={labelCls}>Wins</label>
                  <input type="number" min={0} value={fWins} onChange={(e) => setFWins(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Losses</label>
                  <input type="number" min={0} value={fLosses} onChange={(e) => setFLosses(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Draws</label>
                  <input type="number" min={0} value={fDraws} onChange={(e) => setFDraws(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>KOs</label>
                  <input type="number" min={0} value={fKos} onChange={(e) => setFKos(e.target.value)} className={inputCls} />
                </div>
              </div>
              {fighter && (
                <p className="text-xs text-neutral-500 mt-1">
                  Record: {fighter.record_wins}W – {fighter.record_losses}L – {fighter.record_draws}D ({fighter.record_kos} KOs)
                </p>
              )}
            </fieldset>

            {/* Titles */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Titles &amp; Championships</legend>
              {titles.length > 0 ? (
                <div className="space-y-2">
                  {titles.map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-4 py-2.5"
                    >
                      <div>
                        <p className="text-sm font-medium text-neutral-200">{t.name}</p>
                        <p className="text-xs text-neutral-500">
                          {t.organization && <span>{t.organization} · </span>}
                          {t.weight_class && <span className="capitalize">{label(t.weight_class)} · </span>}
                          {t.won_on && <span>Won {t.won_on} · </span>}
                          <span className="capitalize">{t.status}</span>
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-neutral-600">No titles yet.</p>
              )}

              {!showTitleForm ? (
                <button
                  type="button"
                  onClick={() => setShowTitleForm(true)}
                  className="text-xs text-emerald-400 hover:text-emerald-300"
                >
                  + Add title
                </button>
              ) : (
                <div className="space-y-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className={labelCls}>Title Name *</label>
                      <input type="text" value={tName} onChange={(e) => setTName(e.target.value)} placeholder="e.g. WBC World Champion" className={inputCls} />
                    </div>
                    <div>
                      <label className={labelCls}>Organization</label>
                      <input type="text" value={tOrg} onChange={(e) => setTOrg(e.target.value)} placeholder="e.g. WBC" className={inputCls} />
                    </div>
                    <div>
                      <label className={labelCls}>Weight Class</label>
                      <select value={tWeightClass} onChange={(e) => setTWeightClass(e.target.value)} className={selectCls}>
                        <option value="">—</option>
                        {WEIGHT_CLASSES.map((w) => (
                          <option key={w} value={w}>{label(w)}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className={labelCls}>Won On</label>
                      <input type="date" value={tWonOn} onChange={(e) => setTWonOn(e.target.value)} className={inputCls} />
                    </div>
                    <div>
                      <label className={labelCls}>Status</label>
                      <select value={tStatus} onChange={(e) => setTStatus(e.target.value as TitleStatus)} className={selectCls}>
                        <option value="active">Active</option>
                        <option value="lost">Lost</option>
                        <option value="vacated">Vacated</option>
                        <option value="retired">Retired</option>
                      </select>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleAddTitle}
                      disabled={addingTitle || !tName.trim()}
                      className="rounded-lg bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
                    >
                      {addingTitle ? "Adding…" : "Add Title"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowTitleForm(false)}
                      className="rounded-lg border border-white/10 px-4 py-1.5 text-xs text-neutral-400 hover:bg-white/[0.04]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </fieldset>

            {/* External IDs */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>External IDs</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className={labelCls}>BoxRec ID</label>
                  <input type="text" value={fBoxrecId} onChange={(e) => setFBoxrecId(e.target.value)} placeholder="BoxRec profile ID" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>USA Boxing ID</label>
                  <input type="text" value={fUsaBoxingId} onChange={(e) => setFUsaBoxingId(e.target.value)} placeholder="USA Boxing number" className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Bio & Notes */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Bio &amp; Notes</legend>
              <div>
                <label className={labelCls}>Bio</label>
                <textarea value={fBio} onChange={(e) => setFBio(e.target.value)} rows={3} placeholder="Fighter biography…" className={inputCls + " resize-y"} />
              </div>
              <div>
                <label className={labelCls}>Notes</label>
                <textarea value={fNotes} onChange={(e) => setFNotes(e.target.value)} rows={2} placeholder="Internal notes…" className={inputCls + " resize-y"} />
              </div>
            </fieldset>
          </>
        )}

        {/* ═══════════════════ COACH SECTIONS ═══════════════════ */}
        {user.role === "coach" && coach && (
          <>
            {/* Personal */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Personal Information</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className={labelCls}>Date of Birth</label>
                  <input type="date" value={cDob} onChange={(e) => setCDob(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Sex</label>
                  <select value={cSex} onChange={(e) => setCSex(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {SEXES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Nationality</label>
                  <input type="text" value={cNationality} onChange={(e) => setCNationality(e.target.value)} placeholder="e.g. Lebanese" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Phone</label>
                  <input type="tel" value={cPhone} onChange={(e) => setCPhone(e.target.value)} placeholder="+1 555-0100" className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Coaching */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Coaching Details</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className={labelCls}>Coaching Level</label>
                  <select value={cCoachingLevel} onChange={(e) => setCCoachingLevel(e.target.value)} className={selectCls}>
                    <option value="">—</option>
                    {COACHING_LEVELS.map((l) => (
                      <option key={l} value={l}>{label(l)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Years Experience</label>
                  <input type="number" min={0} value={cYearsExp} onChange={(e) => setCYearsExp(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Specialties</label>
                  <input type="text" value={cSpecialties} onChange={(e) => setCSpecialties(e.target.value)} placeholder="e.g. Striking, Defense" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Languages</label>
                  <input type="text" value={cLanguages} onChange={(e) => setCLanguages(e.target.value)} placeholder="e.g. English, Arabic" className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Certifications & License */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Certifications &amp; License</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className={labelCls}>Certifications</label>
                  <textarea value={cCertifications} onChange={(e) => setCCertifications(e.target.value)} rows={2} placeholder="List certifications, one per line…" className={inputCls + " resize-y"} />
                </div>
                <div>
                  <label className={labelCls}>License Number</label>
                  <input type="text" value={cLicenseNumber} onChange={(e) => setCLicenseNumber(e.target.value)} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>License Expiry</label>
                  <input type="date" value={cLicenseExpiry} onChange={(e) => setCLicenseExpiry(e.target.value)} className={inputCls} />
                </div>
              </div>
            </fieldset>

            {/* Achievements */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Achievements</legend>
              <div>
                <label className={labelCls}>Notable Fighters Trained</label>
                <textarea value={cNotableFighters} onChange={(e) => setCNotableFighters(e.target.value)} rows={2} placeholder="List notable fighters…" className={inputCls + " resize-y"} />
              </div>
            </fieldset>

            {/* Bio & Notes */}
            <fieldset className={sectionCls}>
              <legend className={legendCls}>Bio &amp; Notes</legend>
              <div>
                <label className={labelCls}>Bio</label>
                <textarea value={cBio} onChange={(e) => setCBio(e.target.value)} rows={3} placeholder="Coach biography…" className={inputCls + " resize-y"} />
              </div>
              <div>
                <label className={labelCls}>Notes</label>
                <textarea value={cNotes} onChange={(e) => setCNotes(e.target.value)} rows={2} placeholder="Internal notes…" className={inputCls + " resize-y"} />
              </div>
            </fieldset>
          </>
        )}

        {/* ═══════════════════ ACCOUNT DETAILS (read-only) ═══════════════════ */}
        <fieldset className={sectionCls}>
          <legend className={legendCls}>Account Details</legend>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs text-neutral-500">Role</p>
              <p className="capitalize text-neutral-300">
                {user.role === "gym_manager" ? "Gym Manager" : user.role}
              </p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Member Since</p>
              <p className="text-neutral-300">{new Date(user.created_at).toLocaleDateString()}</p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Status</p>
              <p className={user.is_active ? "text-emerald-400" : "text-red-400"}>
                {user.is_active ? "Active" : "Disabled"}
              </p>
            </div>
            {user.profile_id && (
              <div>
                <p className="text-xs text-neutral-500">System ID</p>
                <code className="text-xs font-mono text-neutral-400 select-all">{user.profile_id}</code>
              </div>
            )}
          </div>
        </fieldset>

        {/* Messages */}
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">
            {error}
          </div>
        )}
        {success && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-400">
            {success}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save Changes"}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-xl border border-white/10 px-4 py-2.5 text-sm text-neutral-400 hover:bg-white/[0.04]"
          >
            Back
          </button>
        </div>
      </form>
    </div>
  );
}
