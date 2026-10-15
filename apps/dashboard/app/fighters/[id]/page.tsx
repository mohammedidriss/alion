"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdviceNotice } from "@/components/AdviceNotice";
import { FighterDashboard } from "@/components/FighterDashboard";
import { ConfirmModal } from "@/components/ConfirmModal";
import { GymInvitationNotice } from "@/components/GymInvitationNotice";
import { PolarH10Card } from "@/components/PolarH10Card";
import { Sparkline } from "@/components/Sparkline";
import { SafetyBoundary } from "@/components/SafetyBoundary";
import { NextStep } from "@/components/NextStep";
import { useAuth } from "@/lib/auth";
import {
  api,
  type Allergy,
  type Fighter,
  type Hand,
  type MedicalCondition,
  type Medication,
  type PunchEvent,
  type Session,
  type SkillLevel,
  type Stance,
  type WeighIn,
  type WeightAnalysis,
} from "@/lib/api";

interface SessionWithStats {
  session: Session;
  events: PunchEvent[];
  totalPunches: number;
  peakVelocity: number;
  meanVelocity: number;
}

export default function FighterPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const router = useRouter();
  const { user } = useAuth();
  // A researcher sees and changes everything (ADR-046); a physician only reads here.
  const canEdit = !!user && ((user.role !== "fighter" && user.role !== "physician") || user.is_researcher);
  const isAdmin = user?.role === "admin"; // an admin without the researcher's access
  const canCreateSession =
    (canEdit && user?.role !== "gym_manager" && !isAdmin) ||
    (user?.role === "fighter" && user?.profile_id === id);
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [sessions, setSessions] = useState<SessionWithStats[]>([]);
  const [weighIns, setWeighIns] = useState<WeighIn[]>([]);
  const [confirmDeleteSession, setConfirmDeleteSession] = useState<string | null>(null);
  const [newWeight, setNewWeight] = useState("");
  const [newWeightNotes, setNewWeightNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [severeAllergies, setSevereAllergies] = useState<Allergy[]>([]);
  const [activeConds, setActiveConds] = useState<MedicalCondition[]>([]);
  const [activeMeds, setActiveMeds] = useState<Medication[]>([]);
  const [weightAnalysis, setWeightAnalysis] = useState<WeightAnalysis | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisErr, setAnalysisErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // Admin only loads general fighter info — no sessions, no medical data
      const isAdminRole = user?.role === "admin";
      const [f, sList, wList] = await Promise.all([
        api.getFighter(id),
        isAdminRole ? Promise.resolve([]) : api.listSessions(id, { recorded: true }),
        isAdminRole ? Promise.resolve([]) : api.listWeighIns(id),
      ]);
      setFighter(f);
      setWeighIns(wList);
      if (!isAdminRole) {
      const withStats = await Promise.all(
        sList
          .slice()
          .sort((a, b) => a.started_at.localeCompare(b.started_at))
          .map(async (s) => {
            const evs = await api.listEvents(s.id).catch(() => [] as PunchEvent[]);
            const vels = evs.map((e) => e.velocity_ms);
            return {
              session: s,
              events: evs,
              totalPunches: evs.length,
              peakVelocity: vels.length ? Math.max(...vels) : 0,
              meanVelocity: vels.length ? vels.reduce((s, v) => s + v, 0) / vels.length : 0,
            };
          }),
      );
      setSessions(withStats);
      }
      // Medical alerts for the dashboard banner (HIPAA: skip for gym managers and admins)
      if (user?.role !== "gym_manager" && user?.role !== "admin") {
        const [allergies, meds, conds] = await Promise.all([
          api.listAllergies(id).catch(() => [] as Allergy[]),
          api.listMedications(id).catch(() => [] as Medication[]),
          api.listConditions(id).catch(() => [] as MedicalCondition[]),
        ]);
        setSevereAllergies(
          allergies.filter(
            (a) => a.severity === "severe" || a.severity === "anaphylactic",
          ),
        );
        setActiveConds(conds.filter((c) => c.status === "active"));
        setActiveMeds(meds.filter((m) => m.is_active));
      }
    } catch (e) {
      setErr(String(e));
    }
    // Reloads once the login is known, so the medical banner follows the role.
  }, [id, user?.role]);

  useEffect(() => {
    load();
  }, [load]);

  const aggregate = useMemo(() => {
    const completed = sessions.filter((x) => x.session.status === "completed");
    const all = completed.flatMap((x) => x.events);
    const allVels = all.map((e) => e.velocity_ms);
    const totalDurationMs = completed.reduce((s, x) => s + x.session.duration_ms, 0);
    const punchesPerSession = completed.map((x) => x.totalPunches);
    const peakPerSession = completed.map((x) => x.peakVelocity);
    return {
      totalSessions: sessions.length,
      completedSessions: completed.length,
      totalPunches: all.length,
      totalDurationS: totalDurationMs / 1000,
      peakVelocity: allVels.length ? Math.max(...allVels) : 0,
      meanVelocity: allVels.length ? allVels.reduce((s, v) => s + v, 0) / allVels.length : 0,
      punchesPerSession,
      peakPerSession,
      bestByPunches: completed
        .slice()
        .sort((a, b) => b.totalPunches - a.totalPunches)
        .slice(0, 3),
      bestByPeak: completed
        .slice()
        .filter((x) => x.peakVelocity > 0)
        .sort((a, b) => b.peakVelocity - a.peakVelocity)
        .slice(0, 3),
    };
  }, [sessions]);

  if (!fighter) {
    return (
      <div className="text-sm text-neutral-400">
        {err ? <span className="text-red-400">{err}</span> : "Loading…"}
      </div>
    );
  }

  const age = fighter.dob
    ? Math.floor(
        (Date.now() - new Date(fighter.dob).getTime()) / (365.25 * 24 * 60 * 60 * 1000),
      )
    : null;

  const addWeighIn = async () => {
    const w = parseFloat(newWeight);
    if (!w || w <= 0) return;
    try {
      await api.createWeighIn(id, w, newWeightNotes.trim() || undefined);
      setNewWeight("");
      setNewWeightNotes("");
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  const deleteWeighIn = async (weighInId: number) => {
    try {
      await api.deleteWeighIn(id, weighInId);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  const deleteSession = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      setConfirmDeleteSession(null);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  // One clear next step (ADR-031): record a session, or look back at the last one.
  const last = sessions
    .map((x) => x.session)
    .filter((s) => s.status === "completed")
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  const startSession = async () => {
    const s = await api.createSession(fighter.id, "live_webcam", "mediapipe");
    router.push(`/sessions/${s.id}`);
  };
  const lastDate = last ? new Date(last.started_at).toLocaleDateString() : "";
  const nextStep = isAdmin ? null : user?.role === "fighter" && last ? (
    <NextStep
      title="Review your last session"
      text={`${lastDate}: your punches, heart rate and wrist force, round by round.`}
      primary={{ label: "Review your last session", href: `/sessions/${last.id}` }}
      secondary={
        canCreateSession
          ? { label: "Start a training session", onClick: startSession }
          : { label: "See your progress", href: `/fighters/${id}/observations` }
      }
    />
  ) : canCreateSession ? (
    <NextStep
      title={user?.role === "fighter" ? "Start your first training session" : `Start a training session with ${fighter.name}`}
      text="Connect the cameras and the sensors, then record when everyone's ready."
      primary={{ label: "Start a training session", onClick: startSession }}
      secondary={last ? { label: `Review the last session (${lastDate})`, href: `/sessions/${last.id}` } : null}
    />
  ) : last ? (
    <NextStep
      title="Review the last session"
      text={`${lastDate}: punches, heart rate and wrist force, round by round.`}
      primary={{ label: "Review the last session", href: `/sessions/${last.id}` }}
    />
  ) : null;

  return (
    <div className="space-y-8 px-4 py-5 sm:px-8 sm:py-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-baseline gap-3">
            <h1 className="truncate text-3xl font-semibold">{fighter.name}</h1>
            {fighter.nickname && (
              <span className="text-lg text-neutral-400">&ldquo;{fighter.nickname}&rdquo;</span>
            )}
          </div>
          <p className="mt-1 text-sm text-neutral-400">
            {fighter.stance}
            {fighter.skill_level ? ` · ${labelForSkill(fighter.skill_level)}` : ""}
            {fighter.weight_class ? ` · ${labelForWeightClass(fighter.weight_class)}` : ""}
            {fighter.nationality ? ` · ${fighter.nationality}` : ""}
            {age != null ? ` · ${age} yrs` : ""}
          </p>
          <p className="mt-1 text-xs text-neutral-600">
            System ID: <code className="rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-neutral-500 select-all">{fighter.id}</code>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {!isAdmin && <PolarH10Card />}
        </div>
      </header>
      {user?.role === "fighter" && user.profile_id === id && <GymInvitationNotice />}

      {nextStep}

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      {/* Medical alert banner — surfaces ringside-critical info (HIPAA: hidden from gym managers & admins) */}
      {user?.role !== "gym_manager" && user?.role !== "admin" &&
       (severeAllergies.length > 0 ||
        activeConds.length > 0 ||
        activeMeds.length > 0) && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-red-200">
              Health notes to know
            </h2>
            <Link
              href={`/fighters/${id}/medical`}
              className="text-[10px] uppercase tracking-wider text-red-300/60 hover:text-red-200"
            >
              all health notes →
            </Link>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {severeAllergies.map((a) => (
              <span
                key={a.id}
                className={`rounded-full px-2 py-0.5 font-medium ${
                  a.severity === "anaphylactic"
                    ? "bg-red-600/30 text-red-200"
                    : "bg-red-500/15 text-red-300"
                }`}
              >
                {a.severity}: {a.substance}
              </span>
            ))}
            {activeConds.map((c) => (
              <span
                key={c.id}
                className="rounded-full bg-amber-500/15 px-2 py-0.5 font-medium text-amber-300"
              >
                {c.name}
              </span>
            ))}
            {activeMeds.map((m) => (
              <span
                key={m.id}
                className="rounded-full bg-blue-500/15 px-2 py-0.5 font-medium text-blue-300"
              >
                {m.name} {m.dose ?? ""}
              </span>
            ))}
          </div>
          <SafetyBoundary className="mt-3" />
        </div>
      )}

      {/* Session/performance data hidden from admin — admin manages accounts, not training data */}
      {!isAdmin && <FighterDashboard
        fighterId={fighter.id}
        sessionsWithEvents={sessions.map((s) => ({
          session: s.session,
          events: s.events,
        }))}
      />}

      {/* BEST SESSIONS — training data, hidden from admin */}
      {!isAdmin && (
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <BestList
          title="Most punches"
          rows={aggregate.bestByPunches}
          metric={(s) => `${s.totalPunches}`}
          metricLabel="punches"
        />
        <BestList
          title="Hardest punch (peak velocity)"
          rows={aggregate.bestByPeak}
          metric={(s) => `${s.peakVelocity.toFixed(2)} m/s`}
          metricLabel="peak"
        />
      </section>
      )}

      {/* PROFILE: record, physical, professional */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Record</h2>
          <p className="mt-2 text-2xl font-semibold">
            {fighter.record_wins}
            <span className="text-neutral-500"> · </span>
            {fighter.record_losses}
            <span className="text-neutral-500"> · </span>
            {fighter.record_draws}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            wins · losses · draws · {fighter.record_kos} KO
            {fighter.record_kos === 1 ? "" : "s"}
          </p>
          {fighter.years_training != null && (
            <p className="mt-3 text-xs text-neutral-400">
              {fighter.years_training} yr{fighter.years_training === 1 ? "" : "s"} training
            </p>
          )}
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Physical</h2>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <Field label="Height" value={fighter.height_cm ? `${fighter.height_cm} cm` : null} />
            <Field label="Reach" value={fighter.reach_cm ? `${fighter.reach_cm} cm` : null} />
            <Field
              label="Weight"
              value={fighter.weight_kg ? `${fighter.weight_kg.toFixed(1)} kg` : null}
            />
            <Field
              label="Shoulder width"
              value={fighter.shoulder_width_cm ? `${fighter.shoulder_width_cm} cm` : null}
            />
            <Field
              label="Dominant hand"
              value={fighter.dominant_hand}
            />
            <Field label="Sex" value={fighter.sex} />
          </dl>
        </div>

        <div className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Professional</h2>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <Field
              label="Skill level"
              value={fighter.skill_level ? labelForSkill(fighter.skill_level) : null}
            />
            <Field
              label="Weight class"
              value={
                fighter.weight_class ? labelForWeightClass(fighter.weight_class) : null
              }
            />
            <Field label="Gym" value={fighter.gym} />
            <Field label="Trainer" value={fighter.trainer} />
            <Field label="BoxRec ID" value={fighter.boxrec_id} mono />
            <Field label="USA Boxing ID" value={fighter.usa_boxing_id} mono />
          </dl>
          {fighter.notes && (
            <p className="mt-3 whitespace-pre-wrap rounded bg-neutral-900/50 p-3 text-xs text-neutral-300">
              {fighter.notes}
            </p>
          )}
        </div>
      </section>

      {/* WEIGHT TRACKER — hidden from admin */}
      {!isAdmin && <section className="rounded-lg border border-neutral-800 p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="font-medium">Weight tracker</h2>
          <span className="text-xs text-neutral-500">
            {weighIns.length} weigh-in{weighIns.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="mt-3">
          <Sparkline
            values={weighIns.map((w) => w.weight_kg)}
            ariaLabel="Weight over time"
            color="#fbbf24"
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-neutral-800 pt-4">
          <input
            type="number"
            step="0.1"
            placeholder="Weight (kg)"
            value={newWeight}
            onChange={(e) => setNewWeight(e.target.value)}
            className="w-32 rounded bg-neutral-900 p-2 text-sm"
          />
          <input
            placeholder="Notes (optional)"
            value={newWeightNotes}
            onChange={(e) => setNewWeightNotes(e.target.value)}
            className="flex-1 rounded bg-neutral-900 p-2 text-sm"
          />
          <button
            onClick={addWeighIn}
            disabled={!newWeight}
            className="rounded bg-emerald-600 px-3 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            Log weigh-in
          </button>
        </div>

        {weighIns.length > 0 && (
          <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-sm">
            {weighIns
              .slice()
              .reverse()
              .map((w) => (
                <li
                  key={w.id}
                  className="flex items-baseline gap-3 border-t border-neutral-900 py-1.5 first:border-t-0"
                >
                  <span className="font-mono">{w.weight_kg.toFixed(1)} kg</span>
                  <span className="text-xs text-neutral-500">
                    {new Date(w.recorded_at).toLocaleString()}
                  </span>
                  {w.notes && (
                    <span className="flex-1 text-xs text-neutral-400">— {w.notes}</span>
                  )}
                  <button
                    onClick={() => deleteWeighIn(w.id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    delete
                  </button>
                </li>
              ))}
          </ul>
        )}

        {/* Weight Analysis */}
        <div className="mt-4 border-t border-neutral-800 pt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-neutral-300">AI Weight Analysis</h3>
            <button
              onClick={async () => {
                setAnalysisLoading(true);
                setAnalysisErr(null);
                try {
                  const result = await api.weightAnalysis(id);
                  setWeightAnalysis(result);
                } catch (e) {
                  setAnalysisErr(e instanceof Error ? e.message : "Analysis failed");
                } finally {
                  setAnalysisLoading(false);
                }
              }}
              disabled={analysisLoading || weighIns.length < 2}
              className="rounded-lg bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-500/25 disabled:opacity-40"
            >
              {analysisLoading ? "Analysing..." : weighIns.length < 2 ? "Need 2+ weigh-ins" : "Analyse weight"}
            </button>
          </div>

          {analysisErr && (
            <p className="mt-2 rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              {analysisErr}
            </p>
          )}

          {weightAnalysis && (
            <div className="mt-3 space-y-3">
              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <MiniStat label="Current" value={weightAnalysis.current_kg != null ? `${weightAnalysis.current_kg.toFixed(1)} kg` : "—"} />
                <MiniStat label="Range" value={weightAnalysis.range_kg != null ? `${weightAnalysis.range_kg.toFixed(1)} kg` : "—"} />
                <MiniStat label="Trend" value={
                  weightAnalysis.trend_direction === "gaining" ? `↑ ${Math.abs(weightAnalysis.trend_kg_per_week ?? 0).toFixed(2)} kg/wk` :
                  weightAnalysis.trend_direction === "losing" ? `↓ ${Math.abs(weightAnalysis.trend_kg_per_week ?? 0).toFixed(2)} kg/wk` :
                  "Stable"
                } />
                <MiniStat label="Variability" value={weightAnalysis.cv_pct != null ? `${weightAnalysis.cv_pct.toFixed(1)}%` : "—"} />
              </div>

              {/* Instability warning */}
              {weightAnalysis.instability_flag && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
                  <p className="text-xs font-medium text-amber-300">⚠ Weight instability detected</p>
                  <p className="mt-0.5 text-[11px] text-amber-400/70">
                    Significant fluctuations found in your weigh-in history. See AI recommendations below.
                  </p>
                </div>
              )}

              {/* AI Summary */}
              <div className="rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
                <p className="text-xs font-medium text-neutral-300">Summary</p>
                <p className="mt-1 text-sm text-neutral-400">{weightAnalysis.ai_summary}</p>
                <AdviceNotice withheld={weightAnalysis.ai_status === "withheld"} />
              </div>

              {/* AI Recommendations */}
              {weightAnalysis.ai_recommendations.length > 0 && (
                <div className="rounded-lg border border-white/5 bg-white/[0.02] px-4 py-3">
                  <p className="text-xs font-medium text-neutral-300">Recommendations</p>
                  <ul className="mt-2 space-y-1.5">
                    {weightAnalysis.ai_recommendations.map((rec, i) => (
                      <li key={i} className="flex gap-2 text-sm text-neutral-400">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-[10px] font-bold text-amber-300">
                          {i + 1}
                        </span>
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </section>}


      {confirmDeleteSession && (
        <ConfirmModal
          title="Delete this session?"
          body="It disappears from the lists. The recording — video, pose, heart rate and wrist-sensor data — is kept for the study; a researcher can restore it."
          onCancel={() => setConfirmDeleteSession(null)}
          onConfirm={() => deleteSession(confirmDeleteSession)}
        />
      )}
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd
        className={`mt-0.5 ${mono ? "font-mono text-xs" : "text-sm"} ${
          value ? "text-neutral-100" : "text-neutral-600"
        }`}
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}


function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-center">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-neutral-200">{value}</p>
    </div>
  );
}

function BestList({
  title,
  rows,
  metric,
  metricLabel,
}: {
  title: string;
  rows: SessionWithStats[];
  metric: (s: SessionWithStats) => string;
  metricLabel: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="font-medium">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">Not enough data yet.</p>
      ) : (
        <ol className="mt-3 space-y-1 text-sm">
          {rows.map((x, i) => (
            <li key={x.session.id} className="flex items-center gap-3">
              <span className="font-mono text-xs text-neutral-500">{i + 1}.</span>
              <Link
                href={`/sessions/${x.session.id}`}
                className="flex-1 hover:underline"
              >
                <span className="font-mono text-xs text-neutral-500">
                  {x.session.id.slice(0, 8)}
                </span>{" "}
                · {new Date(x.session.started_at).toLocaleDateString()}
              </Link>
              <span className="font-mono">
                {metric(x)}{" "}
                <span className="text-xs text-neutral-500">{metricLabel}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}


function labelForSkill(s: SkillLevel): string {
  return s.replace(/_/g, " ");
}

function labelForWeightClass(s: string): string {
  return s.replace(/_/g, " ");
}
