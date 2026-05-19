"use client";

import { useEffect, useState } from "react";
import {
  api,
  type Allergy,
  type AllergySeverity,
  type ConditionStatus,
  type MedicalCondition,
  type MedicalRecord,
  type MedicalRecordPatch,
  type Medication,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const SEVERITY_TINT: Record<AllergySeverity, string> = {
  mild: "bg-yellow-500/15 text-yellow-300",
  moderate: "bg-orange-500/15 text-orange-300",
  severe: "bg-red-500/15 text-red-300",
  anaphylactic: "bg-red-600/30 text-red-200",
};

const STATUS_TINT: Record<ConditionStatus, string> = {
  active: "bg-red-500/15 text-red-300",
  managed: "bg-amber-500/15 text-amber-300",
  recovered: "bg-emerald-500/15 text-emerald-300",
};


export default function MedicalTab({ params }: { params: { id: string } }) {
  const fighterId = params.id;
  const { user } = useAuth();
  const [record, setRecord] = useState<MedicalRecord | null>(null);
  const [allergies, setAllergies] = useState<Allergy[]>([]);
  const [medications, setMedications] = useState<Medication[]>([]);
  const [conditions, setConditions] = useState<MedicalCondition[]>([]);
  const [editingOverview, setEditingOverview] = useState(false);
  const [draft, setDraft] = useState<MedicalRecordPatch>({});
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [r, a, m, c] = await Promise.all([
        api.getMedicalRecord(fighterId),
        api.listAllergies(fighterId),
        api.listMedications(fighterId),
        api.listConditions(fighterId),
      ]);
      setRecord(r);
      setAllergies(a);
      setMedications(m);
      setConditions(c);
      if (r) setDraft(r);
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, [fighterId]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveOverview = async () => {
    try {
      const updated = await api.upsertMedicalRecord(fighterId, draft);
      setRecord(updated);
      setDraft(updated);
      setEditingOverview(false);
    } catch (e) {
      setErr(String(e));
    }
  };

  // HIPAA compliance: gym managers and admins cannot view medical records without fighter consent
  if (user?.role === "gym_manager" || user?.role === "admin") {
    return (
      <div className="space-y-4 px-4 py-8 sm:px-8 sm:py-12">
        <div className="text-4xl">🔒</div>
        <h1 className="text-xl font-semibold">Access Restricted</h1>
        <p className="max-w-md text-sm text-neutral-400">
          Medical records are protected health information. Gym managers cannot
          view fighter medical data without explicit consent, in accordance with
          HIPAA privacy regulations.
        </p>
        <p className="max-w-md text-xs text-neutral-500">
          If you need access for safety reasons (e.g. ringside emergencies),
          request the fighter or their coach to share relevant medical alerts.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header>
        <h1 className="text-2xl font-semibold">Medical</h1>
        <p className="text-sm text-neutral-400">
          Allergies, current medications, conditions, and contact info.
          Confidential — local-only storage.
        </p>
      </header>

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      {/* CRITICAL BANNER — surfaces life-threatening info immediately */}
      {(() => {
        const danger = allergies.filter(
          (a) => a.severity === "severe" || a.severity === "anaphylactic",
        );
        const activeCond = conditions.filter((c) => c.status === "active");
        const activeMeds = medications.filter((m) => m.is_active);
        if (
          danger.length === 0 &&
          activeCond.length === 0 &&
          activeMeds.length === 0
        ) {
          return null;
        }
        return (
          <div className="card border-red-500/30 bg-red-500/5">
            <div className="flex items-baseline justify-between">
              <h2 className="text-base font-semibold text-red-200">
                Critical info
              </h2>
              <span className="text-[10px] uppercase tracking-wider text-red-300/60">
                ringside-relevant
              </span>
            </div>
            <ul className="mt-3 space-y-2 text-sm">
              {danger.map((a) => (
                <li key={a.id} className="flex items-center gap-2">
                  <span className={`pill ${SEVERITY_TINT[a.severity]}`}>
                    {a.severity}
                  </span>
                  <span className="font-medium text-neutral-100">
                    Allergy: {a.substance}
                  </span>
                  {a.notes && (
                    <span className="text-xs text-neutral-400">
                      — {a.notes}
                    </span>
                  )}
                </li>
              ))}
              {activeCond.map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <span className={`pill ${STATUS_TINT[c.status]}`}>
                    {c.status}
                  </span>
                  <span className="font-medium text-neutral-100">
                    Condition: {c.name}
                  </span>
                </li>
              ))}
              {activeMeds.length > 0 && (
                <li className="flex items-center gap-2">
                  <span className="pill bg-violet-500/15 text-violet-300">
                    {activeMeds.length} active
                  </span>
                  <span className="text-neutral-300">
                    Currently on: {activeMeds.map((m) => m.name).join(", ")}
                  </span>
                </li>
              )}
            </ul>
          </div>
        );
      })()}

      {/* Allergies — anaphylaxis-critical, top of detail list */}
      <AllergiesSection
        items={allergies}
        onAdd={async (data) => {
          await api.addAllergy(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteAllergy(fighterId, id);
          refresh();
        }}
      />

      {/* Conditions — existing health context, important for trainers/refs */}
      <ConditionsSection
        items={conditions}
        onAdd={async (data) => {
          await api.addCondition(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteCondition(fighterId, id);
          refresh();
        }}
      />

      {/* Medications — current prescriptions, drug-interaction relevant */}
      <MedicationsSection
        items={medications}
        onAdd={async (data) => {
          await api.addMedication(fighterId, data);
          refresh();
        }}
        onDelete={async (id) => {
          await api.deleteMedication(fighterId, id);
          refresh();
        }}
      />

      {/* Overview / contact / clearance — admin info, kept near the bottom */}
      <section className="card" id="medical-overview">
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold">Overview</h2>
          {!editingOverview ? (
            <button
              onClick={() => {
                setDraft(record ?? {});
                setEditingOverview(true);
              }}
              className="text-xs text-emerald-400 hover:underline"
            >
              edit
            </button>
          ) : null}
        </div>
        {editingOverview ? (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Blood type"
              value={draft.blood_type ?? ""}
              onChange={(v) => setDraft({ ...draft, blood_type: v || null })}
              placeholder="e.g. A+, O-"
            />
            <Input
              label="Last clearance date"
              type="date"
              value={draft.last_clearance_date ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, last_clearance_date: v || null })
              }
            />
            <Input
              label="Clearing physician"
              value={draft.clearing_physician ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, clearing_physician: v || null })
              }
            />
            <Input
              label="Primary physician"
              value={draft.primary_physician ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, primary_physician: v || null })
              }
            />
            <Input
              label="Primary physician phone"
              value={draft.primary_physician_phone ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, primary_physician_phone: v || null })
              }
            />
            <Input
              label="Insurance provider"
              value={draft.insurance_provider ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, insurance_provider: v || null })
              }
            />
            <Input
              label="Insurance policy"
              value={draft.insurance_policy ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, insurance_policy: v || null })
              }
            />
            <Input
              label="Emergency contact name"
              value={draft.emergency_contact_name ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, emergency_contact_name: v || null })
              }
            />
            <Input
              label="Relation"
              value={draft.emergency_contact_relation ?? ""}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  emergency_contact_relation: v || null,
                })
              }
              placeholder="e.g. spouse, parent"
            />
            <Input
              label="Emergency contact phone"
              value={draft.emergency_contact_phone ?? ""}
              onChange={(v) =>
                setDraft({ ...draft, emergency_contact_phone: v || null })
              }
            />
            <div className="sm:col-span-2">
              <label className="text-xs text-neutral-400">Notes</label>
              <textarea
                rows={3}
                value={draft.notes ?? ""}
                onChange={(e) =>
                  setDraft({ ...draft, notes: e.target.value })
                }
                className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <button
                onClick={saveOverview}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setDraft(record ?? {});
                  setEditingOverview(false);
                }}
                className="rounded-xl bg-neutral-800 px-3 py-2 text-sm hover:bg-neutral-700"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : record ? (
          <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Blood type" value={record.blood_type} />
            <Field
              label="Last clearance"
              value={
                record.last_clearance_date
                  ? new Date(record.last_clearance_date).toLocaleDateString()
                  : null
              }
            />
            <Field
              label="Clearing physician"
              value={record.clearing_physician}
            />
            <Field label="Primary physician" value={record.primary_physician} />
            <Field
              label="Primary physician phone"
              value={record.primary_physician_phone}
            />
            <Field label="Insurance" value={record.insurance_provider} />
            <Field
              label="Insurance policy"
              value={record.insurance_policy}
            />
            <Field
              label="Emergency contact"
              value={
                record.emergency_contact_name
                  ? `${record.emergency_contact_name}${
                      record.emergency_contact_relation
                        ? ` (${record.emergency_contact_relation})`
                        : ""
                    }`
                  : null
              }
            />
            <Field
              label="Emergency phone"
              value={record.emergency_contact_phone}
            />
            <div className="sm:col-span-2 lg:col-span-3">
              <dt className="text-xs text-neutral-500">Notes</dt>
              <dd className="mt-0.5 whitespace-pre-wrap text-sm">
                {record.notes ?? "—"}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="mt-3 text-sm text-neutral-500">
            No medical overview yet. Click <em>edit</em> to fill in.
          </p>
        )}
      </section>
    </div>
  );
}

function AllergiesSection({
  items,
  onAdd,
  onDelete,
}: {
  items: Allergy[];
  onAdd: (data: {
    substance: string;
    severity: AllergySeverity;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [substance, setSubstance] = useState("");
  const [severity, setSeverity] = useState<AllergySeverity>("mild");
  const [notes, setNotes] = useState("");

  const submit = async () => {
    if (!substance.trim()) return;
    await onAdd({
      substance: substance.trim(),
      severity,
      notes: notes.trim() || undefined,
    });
    setSubstance("");
    setSeverity("mild");
    setNotes("");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Allergies</h2>
        <button
          onClick={() => setAdding(!adding)}
          className="text-xs text-emerald-400 hover:underline"
        >
          {adding ? "cancel" : "+ add"}
        </button>
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <Input
            label="Substance"
            value={substance}
            onChange={setSubstance}
            placeholder="e.g. peanuts, penicillin"
          />
          <Select
            label="Severity"
            value={severity}
            onChange={(v) => setSeverity(v as AllergySeverity)}
            options={["mild", "moderate", "severe", "anaphylactic"]}
          />
          <Input label="Notes" value={notes} onChange={setNotes} />
          <button
            onClick={submit}
            disabled={!substance.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add allergy
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">None recorded.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span className={`pill ${SEVERITY_TINT[a.severity]}`}>
                {a.severity}
              </span>
              <div className="flex-1">
                <div className="font-medium">{a.substance}</div>
                {a.notes && (
                  <div className="text-xs text-neutral-500">{a.notes}</div>
                )}
              </div>
              <button
                onClick={() => onDelete(a.id)}
                className="text-xs text-neutral-500 hover:text-red-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function MedicationsSection({
  items,
  onAdd,
  onDelete,
}: {
  items: Medication[];
  onAdd: (data: {
    name: string;
    dose?: string;
    frequency?: string;
    started_on?: string;
    prescribed_by?: string;
    is_active?: boolean;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [dose, setDose] = useState("");
  const [frequency, setFrequency] = useState("");
  const [startedOn, setStartedOn] = useState("");
  const [prescribedBy, setPrescribedBy] = useState("");

  const submit = async () => {
    if (!name.trim()) return;
    await onAdd({
      name: name.trim(),
      dose: dose.trim() || undefined,
      frequency: frequency.trim() || undefined,
      started_on: startedOn || undefined,
      prescribed_by: prescribedBy.trim() || undefined,
    });
    setName("");
    setDose("");
    setFrequency("");
    setStartedOn("");
    setPrescribedBy("");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Medications</h2>
        <button
          onClick={() => setAdding(!adding)}
          className="text-xs text-emerald-400 hover:underline"
        >
          {adding ? "cancel" : "+ add"}
        </button>
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <Input label="Name" value={name} onChange={setName} />
          <Input label="Dose" value={dose} onChange={setDose} placeholder="e.g. 200 mg" />
          <Input
            label="Frequency"
            value={frequency}
            onChange={setFrequency}
            placeholder="daily, as needed"
          />
          <Input
            label="Started on"
            type="date"
            value={startedOn}
            onChange={setStartedOn}
          />
          <Input
            label="Prescribed by"
            value={prescribedBy}
            onChange={setPrescribedBy}
          />
          <button
            onClick={submit}
            disabled={!name.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add medication
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">None recorded.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((m) => (
            <li
              key={m.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span
                className={`pill ${
                  m.is_active
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-neutral-700/40 text-neutral-400"
                }`}
              >
                {m.is_active ? "active" : "inactive"}
              </span>
              <div className="flex-1">
                <div className="font-medium">
                  {m.name}
                  {m.dose && (
                    <span className="ml-2 text-xs text-neutral-400">
                      {m.dose}
                    </span>
                  )}
                </div>
                <div className="text-xs text-neutral-500">
                  {[
                    m.frequency,
                    m.started_on
                      ? `since ${new Date(m.started_on).toLocaleDateString()}`
                      : null,
                    m.prescribed_by ? `by ${m.prescribed_by}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </div>
              </div>
              <button
                onClick={() => onDelete(m.id)}
                className="text-xs text-neutral-500 hover:text-red-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ConditionsSection({
  items,
  onAdd,
  onDelete,
}: {
  items: MedicalCondition[];
  onAdd: (data: {
    name: string;
    diagnosed_on?: string;
    status?: ConditionStatus;
    notes?: string;
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [diagnosedOn, setDiagnosedOn] = useState("");
  const [status, setStatus] = useState<ConditionStatus>("active");
  const [notes, setNotes] = useState("");

  const submit = async () => {
    if (!name.trim()) return;
    await onAdd({
      name: name.trim(),
      diagnosed_on: diagnosedOn || undefined,
      status,
      notes: notes.trim() || undefined,
    });
    setName("");
    setDiagnosedOn("");
    setStatus("active");
    setNotes("");
    setAdding(false);
  };

  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Conditions / history</h2>
        <button
          onClick={() => setAdding(!adding)}
          className="text-xs text-emerald-400 hover:underline"
        >
          {adding ? "cancel" : "+ add"}
        </button>
      </div>

      {adding && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 sm:grid-cols-3">
          <Input
            label="Name"
            value={name}
            onChange={setName}
            placeholder="e.g. Concussion (2023), Asthma"
          />
          <Input
            label="Diagnosed on"
            type="date"
            value={diagnosedOn}
            onChange={setDiagnosedOn}
          />
          <Select
            label="Status"
            value={status}
            onChange={(v) => setStatus(v as ConditionStatus)}
            options={["active", "managed", "recovered"]}
          />
          <Input
            label="Notes"
            value={notes}
            onChange={setNotes}
          />
          <button
            onClick={submit}
            disabled={!name.trim()}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black disabled:bg-neutral-700 sm:col-span-3"
          >
            Add condition
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-neutral-500">None recorded.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((c) => (
            <li
              key={c.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span className={`pill ${STATUS_TINT[c.status]}`}>
                {c.status}
              </span>
              <div className="flex-1">
                <div className="font-medium">{c.name}</div>
                <div className="text-xs text-neutral-500">
                  {[
                    c.diagnosed_on
                      ? `diagnosed ${new Date(c.diagnosed_on).toLocaleDateString()}`
                      : null,
                    c.notes,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </div>
              </div>
              <button
                onClick={() => onDelete(c.id)}
                className="text-xs text-neutral-500 hover:text-red-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
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
