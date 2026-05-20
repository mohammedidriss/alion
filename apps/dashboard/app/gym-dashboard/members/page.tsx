"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type CheckIn,
  type Coach,
  type CoachAssignment,
  type Fighter,
  type FighterPatch,
  type GymMembership,
  type Hand,
  type MembershipStatus,
  type SkillLevel,
  type Stance,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const STANCES: Stance[] = ["orthodox", "southpaw", "switch"];
const HANDS: Hand[] = ["left", "right"];
const SKILL_LEVELS: SkillLevel[] = [
  "recreational",
  "amateur_novice",
  "amateur_open",
  "amateur_elite",
  "semi_pro",
  "professional",
  "coach",
];
const SEXES = ["male", "female", "other"];
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

function labelFor(s: string) {
  return s.replace(/_/g, " ");
}

export default function MembersPage() {
  const { user } = useAuth();
  const isGymManager = user?.role === "gym_manager";

  const [gymId, setGymId] = useState<string | null>(null);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterSkill, setFilterSkill] = useState("");
  const [filterStance, setFilterStance] = useState("");

  const [memberships, setMemberships] = useState<GymMembership[]>([]);
  const [todaysCheckins, setTodaysCheckins] = useState<CheckIn[]>([]);
  const [coachAssignments, setCoachAssignments] = useState<Record<string, CoachAssignment[]>>({});

  // Panel state: "none" | "add-fighter" | "import" | "create-account"
  const [activePanel, setActivePanel] = useState<"none" | "add-fighter" | "import" | "create-account">("none");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  // Import by System ID
  const [importId, setImportId] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [importSuccess, setImportSuccess] = useState("");

  // Create new account
  const [accName, setAccName] = useState("");
  const [accEmail, setAccEmail] = useState("");
  const [accPassword, setAccPassword] = useState("");
  const [accRole, setAccRole] = useState<"fighter" | "coach">("fighter");
  const [accCreating, setAccCreating] = useState(false);
  const [accError, setAccError] = useState("");
  const [accSuccess, setAccSuccess] = useState("");

  // Identity
  const [fName, setFName] = useState("");
  const [fNickname, setFNickname] = useState("");
  const [fDob, setFDob] = useState("");
  const [fSex, setFSex] = useState("");
  const [fNationality, setFNationality] = useState("");

  // Boxing
  const [fStance, setFStance] = useState<Stance>("orthodox");
  const [fDominantHand, setFDominantHand] = useState("");
  const [fSkillLevel, setFSkillLevel] = useState<string>("");
  const [fWeightClass, setFWeightClass] = useState("");
  const [fYearsTraining, setFYearsTraining] = useState("");
  const [fTrainer, setFTrainer] = useState("");

  // Physical
  const [fHeightCm, setFHeightCm] = useState("");
  const [fReachCm, setFReachCm] = useState("");
  const [fWeightKg, setFWeightKg] = useState("");
  const [fShoulderCm, setFShoulderCm] = useState("");

  // Record
  const [fWins, setFWins] = useState("");
  const [fLosses, setFLosses] = useState("");
  const [fDraws, setFDraws] = useState("");
  const [fKos, setFKos] = useState("");

  // External IDs
  const [fBoxrecId, setFBoxrecId] = useState("");
  const [fUsaBoxingId, setFUsaBoxingId] = useState("");

  // Notes / Bio
  const [fNotes, setFNotes] = useState("");
  const [fBio, setFBio] = useState("");

  const load = useCallback(async () => {
    if (!isGymManager || !user) return;
    setLoading(true);
    try {
      const me = await api.getMyGymManagerProfile();
      setGymId(me.gym_id);
      const [fs, cs, ms, cis] = await Promise.all([
        api.listFighters(me.gym_id),
        api.listCoaches(me.gym_id),
        api.listGymMembers(me.gym_id),
        api.listTodaysCheckins(me.gym_id).catch(() => [] as CheckIn[]),
      ]);
      setFighters(fs);
      setCoaches(cs);
      setMemberships(ms);
      setTodaysCheckins(cis);
      // Fetch coach assignments for all fighters
      const assignMap: Record<string, CoachAssignment[]> = {};
      await Promise.all(
        fs.map(async (f) => {
          try {
            assignMap[f.id] = await api.listCoachAssignments(f.id);
          } catch {
            assignMap[f.id] = [];
          }
        }),
      );
      setCoachAssignments(assignMap);
    } finally {
      setLoading(false);
    }
  }, [user, isGymManager]);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () =>
      fighters.filter((f) => {
        if (filterSkill && f.skill_level !== filterSkill) return false;
        if (filterStance && f.stance !== filterStance) return false;
        if (q && !f.name.toLowerCase().includes(q)) return false;
        return true;
      }),
    [fighters, filterSkill, filterStance, q],
  );

  const resetForm = () => {
    setFName(""); setFNickname(""); setFDob(""); setFSex(""); setFNationality("");
    setFStance("orthodox"); setFDominantHand(""); setFSkillLevel(""); setFWeightClass("");
    setFYearsTraining(""); setFTrainer("");
    setFHeightCm(""); setFReachCm(""); setFWeightKg(""); setFShoulderCm("");
    setFWins(""); setFLosses(""); setFDraws(""); setFKos("");
    setFBoxrecId(""); setFUsaBoxingId("");
    setFNotes(""); setFBio("");
    setPhotoFile(null); setPhotoPreview(null);
    setCreateError("");
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError("");

    // Re-resolve gymId if state was lost (e.g. Fast Refresh)
    let effectiveGymId = gymId;
    if (!effectiveGymId) {
      try {
        const me = await api.getMyGymManagerProfile();
        effectiveGymId = me.gym_id;
        setGymId(me.gym_id);
      } catch { /* fallthrough to error below */ }
    }

    if (!effectiveGymId) {
      setCreateError("Could not determine your gym. Please refresh the page.");
      return;
    }
    if (!fName.trim()) {
      setCreateError("Fighter name is required.");
      return;
    }

    setCreating(true);
    try {
      const created = await api.createFighter(fName.trim(), fStance, effectiveGymId);

      // Build patch with all extra fields
      const patch: FighterPatch = {};
      if (fNickname) patch.nickname = fNickname;
      if (fDob) patch.dob = fDob;
      if (fSex) patch.sex = fSex;
      if (fNationality) patch.nationality = fNationality;
      if (fDominantHand) patch.dominant_hand = fDominantHand as Hand;
      if (fSkillLevel) patch.skill_level = fSkillLevel as SkillLevel;
      if (fWeightClass) patch.weight_class = fWeightClass;
      if (fYearsTraining) patch.years_training = parseInt(fYearsTraining);
      if (fTrainer) patch.trainer = fTrainer;
      if (fHeightCm) patch.height_cm = parseFloat(fHeightCm);
      if (fReachCm) patch.reach_cm = parseFloat(fReachCm);
      if (fWeightKg) patch.weight_kg = parseFloat(fWeightKg);
      if (fShoulderCm) patch.shoulder_width_cm = parseFloat(fShoulderCm);
      if (fWins) patch.record_wins = parseInt(fWins);
      if (fLosses) patch.record_losses = parseInt(fLosses);
      if (fDraws) patch.record_draws = parseInt(fDraws);
      if (fKos) patch.record_kos = parseInt(fKos);
      if (fBoxrecId) patch.boxrec_id = fBoxrecId;
      if (fUsaBoxingId) patch.usa_boxing_id = fUsaBoxingId;
      if (fNotes) patch.notes = fNotes;
      if (fBio) patch.bio = fBio;

      if (Object.keys(patch).length > 0) {
        await api.updateFighter(created.id, patch);
      }

      // Upload photo if selected
      if (photoFile) {
        await api.uploadFighterPhoto(created.id, photoFile);
      }

      resetForm();
      setActivePanel("none");
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create fighter";
      setCreateError(msg);
    } finally {
      setCreating(false);
    }
  };

  const onPhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhotoFile(file);
      setPhotoPreview(URL.createObjectURL(file));
    }
  };

  // Helpers for membership status
  const getMembership = (memberId: string) =>
    memberships.find((m) => m.member_id === memberId);

  const isCheckedInToday = (memberId: string) =>
    todaysCheckins.some((ci) => ci.member_id === memberId && !ci.checked_out_at);

  const statusBadge = (status: MembershipStatus) => {
    const styles: Record<MembershipStatus, string> = {
      active: "bg-emerald-500/15 text-emerald-300",
      frozen: "bg-blue-500/15 text-blue-300",
      suspended: "bg-red-500/15 text-red-300",
      trial: "bg-amber-500/15 text-amber-300",
      left: "bg-neutral-500/15 text-neutral-400",
    };
    return (
      <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${styles[status] ?? styles.active}`}>
        {status}
      </span>
    );
  };

  const handleStatusChange = async (membershipId: number, newStatus: MembershipStatus, memberId: string) => {
    if (!gymId) return;
    let note: string | null = null;
    if (newStatus === "frozen" || newStatus === "suspended") {
      note = prompt(`Reason for ${newStatus}:`) ?? "";
    }
    try {
      await api.updateMembershipStatus(gymId, membershipId, newStatus, note ?? undefined);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update status");
    }
  };

  const getCurrentCoach = (fighterId: string): CoachAssignment | undefined => {
    const assigns = coachAssignments[fighterId] ?? [];
    return assigns.find((a) => !a.ended_on);
  };

  const handleCoachChange = async (fighterId: string, newCoachId: string) => {
    const current = getCurrentCoach(fighterId);
    try {
      // Remove existing assignment if any
      if (current) {
        await api.deleteCoachAssignment(fighterId, current.id);
      }
      // Add new assignment if not "none"
      if (newCoachId) {
        await api.addCoachAssignment(fighterId, {
          coach_id: newCoachId,
          role: "head_coach",
        });
      }
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update coach");
    }
  };

  const handleCheckIn = async (memberId: string, memberType: "fighter" | "coach") => {
    if (!gymId) return;
    try {
      await api.checkIn(gymId, memberId, memberType);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Check-in failed");
    }
  };

  if (!isGymManager) {
    return (
      <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">
        Sign in as a gym manager to access this page.
      </div>
    );
  }

  if (loading) {
    return <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">Loading members...</div>;
  }

  const inputCls =
    "w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none";
  const labelCls = "mb-1 block text-xs font-medium text-neutral-400";

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Members</h1>
          <p className="text-sm text-neutral-500">
            {fighters.length} fighter{fighters.length !== 1 ? "s" : ""}, {coaches.length} coach{coaches.length !== 1 ? "es" : ""} registered
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setActivePanel(activePanel === "import" ? "none" : "import"); setImportError(""); setImportSuccess(""); setImportId(""); }}
            className={`rounded-xl px-4 py-2 text-sm font-medium ${activePanel === "import" ? "bg-amber-500 text-black" : "border border-amber-500/30 text-amber-300 hover:bg-amber-500/10"}`}
          >
            {activePanel === "import" ? "Cancel" : "Import by ID"}
          </button>
          <button
            onClick={() => { setActivePanel(activePanel === "create-account" ? "none" : "create-account"); setAccError(""); setAccSuccess(""); setAccName(""); setAccEmail(""); setAccPassword(""); setAccRole("fighter"); }}
            className={`rounded-xl px-4 py-2 text-sm font-medium ${activePanel === "create-account" ? "bg-violet-500 text-black" : "border border-violet-500/30 text-violet-300 hover:bg-violet-500/10"}`}
          >
            {activePanel === "create-account" ? "Cancel" : "Create Account"}
          </button>
          <button
            onClick={() => { setActivePanel(activePanel === "add-fighter" ? "none" : "add-fighter"); if (activePanel === "add-fighter") resetForm(); }}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
          >
            {activePanel === "add-fighter" ? "Cancel" : "+ Add Fighter"}
          </button>
        </div>
      </header>

      {/* ─── Import by System ID ────────────────────────────────── */}
      {activePanel === "import" && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-lg font-semibold text-amber-200">Import Existing Member</h3>
            <p className="mt-1 text-xs text-neutral-400">
              Ask the fighter or coach for their System ID, then enter it below to add them to your gym.
            </p>
          </div>
          <div className="flex gap-3">
            <input
              type="text"
              value={importId}
              onChange={(e) => setImportId(e.target.value)}
              placeholder="Paste System ID (e.g. dbf52390-2d23-49b8-b119-82618ea7b4d7)"
              className={`${inputCls} flex-1 font-mono text-xs`}
            />
            <button
              disabled={importing || !importId.trim()}
              onClick={async () => {
                if (!gymId) return;
                setImporting(true);
                setImportError("");
                setImportSuccess("");
                try {
                  const result = await api.importGymMember(gymId, importId.trim());
                  setImportSuccess(`Successfully added ${result.member_name || "member"} (${result.member_type}) to your gym!`);
                  setImportId("");
                  load();
                } catch (err: unknown) {
                  const msg = err instanceof Error ? err.message : "Import failed";
                  setImportError(msg);
                } finally {
                  setImporting(false);
                }
              }}
              className="rounded-xl bg-amber-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-amber-400 disabled:opacity-50"
            >
              {importing ? "Importing..." : "Import"}
            </button>
          </div>
          {importError && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">{importError}</div>
          )}
          {importSuccess && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-400">{importSuccess}</div>
          )}
        </div>
      )}

      {/* ─── Create New Account ─────────────────────────────────── */}
      {activePanel === "create-account" && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-lg font-semibold text-violet-200">Create New Member Account</h3>
            <p className="mt-1 text-xs text-neutral-400">
              Create a system account for a new fighter or coach. They&apos;ll be added to your gym automatically.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className={labelCls}>Name *</label>
              <input type="text" value={accName} onChange={(e) => setAccName(e.target.value)} placeholder="Full name" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Role *</label>
              <select value={accRole} onChange={(e) => setAccRole(e.target.value as "fighter" | "coach")} className={inputCls}>
                <option value="fighter">Fighter</option>
                <option value="coach">Coach</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Email *</label>
              <input type="email" value={accEmail} onChange={(e) => setAccEmail(e.target.value)} placeholder="user@example.com" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Password *</label>
              <input type="text" value={accPassword} onChange={(e) => setAccPassword(e.target.value)} placeholder="Min 6 characters" className={inputCls} />
            </div>
          </div>
          {accError && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">{accError}</div>
          )}
          {accSuccess && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-400">{accSuccess}</div>
          )}
          <div className="flex items-center gap-3">
            <button
              disabled={accCreating || !accName.trim() || !accEmail.trim() || !accPassword}
              onClick={async () => {
                if (!gymId) return;
                setAccCreating(true);
                setAccError("");
                setAccSuccess("");
                try {
                  const result = await api.createGymMemberAccount(gymId, {
                    name: accName.trim(),
                    email: accEmail.trim(),
                    password: accPassword,
                    role: accRole,
                  });
                  setAccSuccess(`Account created for ${result.member_name || accName} (${accRole}). They can now sign in with their email and password.`);
                  setAccName(""); setAccEmail(""); setAccPassword(""); setAccRole("fighter");
                  load();
                } catch (err: unknown) {
                  const msg = err instanceof Error ? err.message : "Account creation failed";
                  setAccError(msg);
                } finally {
                  setAccCreating(false);
                }
              }}
              className="rounded-xl bg-violet-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-violet-400 disabled:opacity-50"
            >
              {accCreating ? "Creating..." : "Create Account & Add to Gym"}
            </button>
            <button
              type="button"
              onClick={() => { setActivePanel("none"); setAccName(""); setAccEmail(""); setAccPassword(""); setAccError(""); setAccSuccess(""); }}
              className="rounded-xl border border-white/10 px-4 py-2.5 text-sm text-neutral-400 hover:bg-white/[0.04]"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ─── Create fighter profile form ────────────────────────── */}
      {activePanel === "add-fighter" && (
        <form onSubmit={handleCreate} className="card space-y-5">
          <h3 className="text-lg font-semibold">New Fighter</h3>

          {/* Photo */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Photo</legend>
            <div className="flex items-center gap-4">
              {photoPreview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photoPreview} alt="preview" className="h-20 w-20 rounded-full object-cover" />
              ) : (
                <div className="flex h-20 w-20 items-center justify-center rounded-full bg-white/[0.06] text-2xl text-neutral-500">
                  {fName ? fName[0].toUpperCase() : "?"}
                </div>
              )}
              <div className="flex-1">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={onPhotoChange}
                  className="text-xs text-neutral-400"
                />
                <p className="mt-1 text-[11px] text-neutral-500">JPG / PNG / WebP, max 5 MB</p>
              </div>
            </div>
          </fieldset>

          {/* Identity */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Identity</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className={labelCls}>Name *</label>
                <input type="text" required value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Fighter name" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Nickname</label>
                <input type="text" value={fNickname} onChange={(e) => setFNickname(e.target.value)} placeholder='e.g. "The Flash"' className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Date of Birth</label>
                <input type="date" value={fDob} onChange={(e) => setFDob(e.target.value)} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Sex</label>
                <select value={fSex} onChange={(e) => setFSex(e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {SEXES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Nationality</label>
                <input type="text" value={fNationality} onChange={(e) => setFNationality(e.target.value)} placeholder="e.g. USA" className={inputCls} />
              </div>
            </div>
          </fieldset>

          {/* Boxing */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Boxing</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className={labelCls}>Stance</label>
                <select value={fStance} onChange={(e) => setFStance(e.target.value as Stance)} className={inputCls}>
                  {STANCES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Dominant Hand</label>
                <select value={fDominantHand} onChange={(e) => setFDominantHand(e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {HANDS.map((h) => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Skill Level</label>
                <select value={fSkillLevel} onChange={(e) => setFSkillLevel(e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {SKILL_LEVELS.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Weight Class</label>
                <select value={fWeightClass} onChange={(e) => setFWeightClass(e.target.value)} className={inputCls}>
                  <option value="">—</option>
                  {WEIGHT_CLASSES.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Years Training</label>
                <input type="number" min="0" max="80" value={fYearsTraining} onChange={(e) => setFYearsTraining(e.target.value)} placeholder="e.g. 5" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Trainer</label>
                <select value={fTrainer} onChange={(e) => setFTrainer(e.target.value)} className={inputCls}>
                  <option value="">— Select coach —</option>
                  {coaches.map((c) => (
                    <option key={c.id} value={c.name}>{c.name}{c.specialties ? ` (${c.specialties})` : ""}</option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          {/* Physical */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Physical</legend>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <div>
                <label className={labelCls}>Height (cm)</label>
                <input type="number" step="0.5" min="80" max="250" value={fHeightCm} onChange={(e) => setFHeightCm(e.target.value)} placeholder="175" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Reach (cm)</label>
                <input type="number" step="0.5" min="80" max="260" value={fReachCm} onChange={(e) => setFReachCm(e.target.value)} placeholder="180" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Weight (kg)</label>
                <input type="number" step="0.1" min="0" max="400" value={fWeightKg} onChange={(e) => setFWeightKg(e.target.value)} placeholder="72.5" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Shoulder Width (cm)</label>
                <input type="number" step="0.5" min="20" max="80" value={fShoulderCm} onChange={(e) => setFShoulderCm(e.target.value)} placeholder="45" className={inputCls} />
              </div>
            </div>
          </fieldset>

          {/* Record */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Record</legend>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <div>
                <label className={labelCls}>Wins</label>
                <input type="number" min="0" value={fWins} onChange={(e) => setFWins(e.target.value)} placeholder="0" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Losses</label>
                <input type="number" min="0" value={fLosses} onChange={(e) => setFLosses(e.target.value)} placeholder="0" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Draws</label>
                <input type="number" min="0" value={fDraws} onChange={(e) => setFDraws(e.target.value)} placeholder="0" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>KOs</label>
                <input type="number" min="0" value={fKos} onChange={(e) => setFKos(e.target.value)} placeholder="0" className={inputCls} />
              </div>
            </div>
          </fieldset>

          {/* External IDs */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">External IDs</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>BoxRec ID</label>
                <input type="text" value={fBoxrecId} onChange={(e) => setFBoxrecId(e.target.value)} className={`${inputCls} font-mono`} />
              </div>
              <div>
                <label className={labelCls}>USA Boxing ID</label>
                <input type="text" value={fUsaBoxingId} onChange={(e) => setFUsaBoxingId(e.target.value)} className={`${inputCls} font-mono`} />
              </div>
            </div>
          </fieldset>

          {/* Bio & Notes */}
          <fieldset className="rounded-xl border border-white/5 p-4">
            <legend className="px-2 text-xs uppercase tracking-wider text-neutral-500">Bio & Notes</legend>
            <div className="space-y-4">
              <div>
                <label className={labelCls}>Bio</label>
                <textarea value={fBio} onChange={(e) => setFBio(e.target.value)} rows={2} placeholder="Short bio for the profile header" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Notes</label>
                <textarea value={fNotes} onChange={(e) => setFNotes(e.target.value)} rows={2} placeholder="Internal notes" className={inputCls} />
              </div>
            </div>
          </fieldset>

          {createError && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">
              {createError}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={creating || !fName.trim()}
              className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
            >
              {creating ? "Creating..." : "Create Fighter"}
            </button>
            <button
              type="button"
              onClick={() => { setActivePanel("none"); resetForm(); }}
              className="rounded-xl border border-white/10 px-4 py-2.5 text-sm text-neutral-400 hover:bg-white/[0.04]"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* ─── Filters ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name..."
            className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">⌕</span>
        </div>
        <select value={filterSkill} onChange={(e) => setFilterSkill(e.target.value)} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-300">
          <option value="">All skill levels</option>
          {SKILL_LEVELS.map((s) => <option key={s} value={s}>{labelFor(s)}</option>)}
        </select>
        <select value={filterStance} onChange={(e) => setFilterStance(e.target.value)} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-300">
          <option value="">All stances</option>
          {STANCES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="text-xs text-neutral-500">{filtered.length} of {fighters.length}</span>
      </div>

      {/* ─── Fighters table ──────────────────────────────────────── */}
      <div className="card overflow-x-auto">
        <h3 className="mb-3 text-sm font-semibold text-neutral-300 uppercase tracking-wider">Fighters</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wider text-neutral-500">
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Coach</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Stance</th>
              <th className="pb-2 pr-4">Skill Level</th>
              <th className="pb-2 pr-4">Weight</th>
              <th className="pb-2 pr-4">Record</th>
              <th className="pb-2 pr-4">Joined</th>
              <th className="pb-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((f) => {
              const ms = getMembership(f.id);
              const checkedIn = isCheckedInToday(f.id);
              return (
                <tr key={f.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  <td className="py-3 pr-4">
                    <Link href={`/fighters/${f.id}`} className="flex items-center gap-2 hover:text-emerald-300">
                      <div className="relative">
                        <ProfileAvatar name={f.name} photo_path={f.photo_path} size={32} />
                        {checkedIn && (
                          <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#0d0d12] bg-emerald-500" title="In gym now" />
                        )}
                      </div>
                      <div>
                        <span className="font-medium">{f.name}</span>
                        {f.nickname && <span className="ml-1.5 text-xs text-neutral-500">&quot;{f.nickname}&quot;</span>}
                      </div>
                    </Link>
                  </td>
                  <td className="py-3 pr-4">
                    <select
                      value={getCurrentCoach(f.id)?.coach_id ?? ""}
                      onChange={(e) => handleCoachChange(f.id, e.target.value)}
                      className="rounded-lg border border-white/10 bg-transparent px-1 py-1 text-[11px] text-neutral-400 focus:outline-none max-w-[120px]"
                    >
                      <option value="">— None —</option>
                      {coaches.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-3 pr-4">
                    <div className="flex flex-col gap-1">
                      {statusBadge((ms?.status ?? "active") as MembershipStatus)}
                      {ms?.status_note && (
                        <span className="text-[10px] text-neutral-500 max-w-[120px] truncate" title={ms.status_note}>
                          {ms.status_note}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 pr-4 capitalize text-neutral-400">{f.stance ?? "—"}</td>
                  <td className="py-3 pr-4 capitalize text-neutral-400">{f.skill_level ? labelFor(f.skill_level) : "—"}</td>
                  <td className="py-3 pr-4 text-neutral-400">{f.weight_kg ? `${f.weight_kg} kg` : "—"}</td>
                  <td className="py-3 pr-4 text-neutral-400">
                    {f.record_wins}-{f.record_losses}-{f.record_draws}
                    {f.record_kos > 0 && <span className="ml-1 text-xs text-neutral-500">({f.record_kos} KO)</span>}
                  </td>
                  <td className="py-3 pr-4 text-neutral-500 text-xs">
                    {ms?.joined_on ? new Date(ms.joined_on).toLocaleDateString() : "—"}
                  </td>
                  <td className="py-3">
                    <div className="flex items-center gap-1.5">
                      {!checkedIn && ms?.status === "active" && (
                        <button
                          onClick={() => handleCheckIn(f.id, "fighter")}
                          className="rounded-lg bg-emerald-500/15 px-2 py-1 text-[10px] font-medium text-emerald-300 hover:bg-emerald-500/25"
                          title="Check in"
                        >
                          Check in
                        </button>
                      )}
                      {checkedIn && (
                        <span className="rounded-lg bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-400">
                          In gym
                        </span>
                      )}
                      {ms && (
                        <select
                          value={ms.status}
                          onChange={(e) => handleStatusChange(ms.id, e.target.value as MembershipStatus, f.id)}
                          className="rounded-lg border border-white/10 bg-transparent px-1 py-1 text-[10px] text-neutral-400 focus:outline-none"
                        >
                          <option value="active">Active</option>
                          <option value="frozen">Frozen</option>
                          <option value="suspended">Suspended</option>
                          <option value="trial">Trial</option>
                          <option value="left">Remove</option>
                        </select>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="py-8 text-center text-neutral-500">
                  {fighters.length === 0 ? "No fighters yet. Add your first member above." : "No fighters match your filters."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ─── Coaches table ──────────────────────────────────────── */}
      {coaches.length > 0 && (
        <div className="card overflow-x-auto">
          <h3 className="mb-3 text-sm font-semibold text-neutral-300 uppercase tracking-wider">Coaches</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wider text-neutral-500">
                <th className="pb-2 pr-4">Name</th>
                <th className="pb-2 pr-4">System ID</th>
                <th className="pb-2 pr-4">Specialties</th>
                <th className="pb-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {coaches.map((c) => (
                <tr key={c.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  <td className="py-3 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-violet-500/20 text-xs font-bold text-violet-300">
                        {c.name[0]?.toUpperCase() ?? "?"}
                      </div>
                      <span className="font-medium">{c.name}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <code className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[10px] font-mono text-neutral-500 select-all">{c.id}</code>
                  </td>
                  <td className="py-3 pr-4 text-neutral-400">{c.specialties || "—"}</td>
                  <td className="py-3 text-neutral-500 text-xs">{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
