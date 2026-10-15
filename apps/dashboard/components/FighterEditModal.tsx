"use client";

/**
 * Editing a fighter's profile — opened from the profile page (your own) or a
 * fighter's Profile tab (someone you may edit). All profile editing happens there,
 * not on the dashboard.
 */

import { useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Fighter, type FighterOptions, type FighterPatch, type Hand, type SkillLevel, type Stance } from "@/lib/api";

const PRO_LEVELS: SkillLevel[] = [
  "recreational",
  "amateur_novice",
  "amateur_open",
  "amateur_elite",
  "semi_pro",
  "professional",
  "coach",
];

export function FighterEditModal({
  fighter,
  options,
  onCancel,
  onSave,
}: {
  fighter: Fighter;
  options: FighterOptions | null;
  onCancel: () => void;
  onSave: (patch: FighterPatch) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Fighter>({ ...fighter });
  const [saving, setSaving] = useState(false);
  const [photoPath, setPhotoPath] = useState<string | null>(fighter.photo_path);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoErr, setPhotoErr] = useState<string | null>(null);
  const set = <K extends keyof Fighter>(k: K, v: Fighter[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const submit = async () => {
    setSaving(true);
    const patch: FighterPatch = {};
    (Object.keys(draft) as (keyof Fighter)[]).forEach((k) => {
      if (k === "id" || k === "created_at") return;
      if (draft[k] !== fighter[k]) (patch as any)[k] = draft[k];
    });
    await onSave(patch);
    setSaving(false);
  };

  const onPickPhoto = async (file: File) => {
    setPhotoBusy(true);
    setPhotoErr(null);
    try {
      const updated = await api.uploadFighterPhoto(fighter.id, file);
      setPhotoPath(updated.photo_path);
    } catch (e) {
      setPhotoErr(String(e));
    } finally {
      setPhotoBusy(false);
    }
  };

  const num = (v: string) => (v === "" ? null : Number(v));

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto bg-black/70 p-4">
      <div className="my-8 h-fit w-full max-w-2xl rounded-lg border border-neutral-800 bg-neutral-950 p-5 shadow-xl">
        <h3 className="text-lg font-medium">Edit profile</h3>

        <div className="mt-4 space-y-5 text-sm">
          <Group title="Photo">
            <div className="flex items-center gap-4">
              <ProfileAvatar
                name={draft.name || fighter.name}
                photo_path={photoPath}
                size={80}
              />
              <div className="flex-1">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  disabled={photoBusy}
                  onChange={(e) =>
                    e.target.files?.[0] && onPickPhoto(e.target.files[0])
                  }
                  className="text-xs"
                />
                <p className="mt-1 text-[11px] text-neutral-500">
                  {photoBusy
                    ? "Uploading…"
                    : "JPG / PNG / WebP, max 5 MB. Saves immediately."}
                </p>
                {photoErr && (
                  <p className="mt-1 text-xs text-red-300">{photoErr}</p>
                )}
              </div>
            </div>
          </Group>

          <Group title="Identity">
            <Row>
              <Lbl>Name</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </Row>
            <Row>
              <Lbl>Nickname</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.nickname ?? ""}
                onChange={(e) => set("nickname", e.target.value || null)}
              />
            </Row>
            <Row>
              <Lbl>DOB</Lbl>
              <input
                type="date"
                className="rounded bg-neutral-900 p-2"
                value={draft.dob ?? ""}
                onChange={(e) => set("dob", e.target.value || null)}
              />
              <Lbl>Sex</Lbl>
              <select
                className="rounded bg-neutral-900 p-2"
                value={draft.sex ?? ""}
                onChange={(e) => set("sex", e.target.value || null)}
              >
                <option value="">—</option>
                {(options?.sexes ?? ["male", "female", "other"]).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Row>
            <Row>
              <Lbl>Nationality</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.nationality ?? ""}
                onChange={(e) => set("nationality", e.target.value || null)}
                placeholder="e.g. KSA"
              />
            </Row>
          </Group>

          <Group title="Boxing">
            <Row>
              <Lbl>Stance</Lbl>
              <select
                className="rounded bg-neutral-900 p-2"
                value={draft.stance}
                onChange={(e) => set("stance", e.target.value as Stance)}
              >
                {(options?.stances ?? ["orthodox", "southpaw", "switch"]).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <Lbl>Dominant hand</Lbl>
              <select
                className="rounded bg-neutral-900 p-2"
                value={draft.dominant_hand ?? ""}
                onChange={(e) =>
                  set("dominant_hand", (e.target.value || null) as Hand | null)
                }
              >
                <option value="">—</option>
                {(options?.hands ?? ["left", "right"]).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Row>
            <Row>
              <Lbl>Skill level</Lbl>
              <select
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.skill_level ?? ""}
                onChange={(e) =>
                  set(
                    "skill_level",
                    (e.target.value || null) as SkillLevel | null,
                  )
                }
              >
                <option value="">—</option>
                {(options?.skill_levels ?? PRO_LEVELS).map((s) => (
                  <option key={s} value={s}>
                    {labelForSkill(s as SkillLevel)}
                  </option>
                ))}
              </select>
            </Row>
            <Row>
              <Lbl>Weight class</Lbl>
              <select
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.weight_class ?? ""}
                onChange={(e) => set("weight_class", e.target.value || null)}
              >
                <option value="">—</option>
                {(options?.weight_classes ?? []).map((s) => (
                  <option key={s} value={s}>
                    {labelForWeightClass(s)}
                  </option>
                ))}
              </select>
            </Row>
            <Row>
              <Lbl>Years training</Lbl>
              <input
                type="number"
                min={0}
                max={80}
                className="w-24 rounded bg-neutral-900 p-2"
                value={draft.years_training ?? ""}
                onChange={(e) => set("years_training", num(e.target.value))}
              />
              <Lbl>Gym</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.gym ?? ""}
                onChange={(e) => set("gym", e.target.value || null)}
              />
            </Row>
            <Row>
              <Lbl>Trainer</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2"
                value={draft.trainer ?? ""}
                onChange={(e) => set("trainer", e.target.value || null)}
              />
            </Row>
          </Group>

          <Group title="Physical">
            <Row>
              <Lbl>Height (cm)</Lbl>
              <input
                type="number"
                step="0.5"
                className="w-24 rounded bg-neutral-900 p-2"
                value={draft.height_cm ?? ""}
                onChange={(e) => set("height_cm", num(e.target.value))}
              />
              <Lbl>Reach (cm)</Lbl>
              <input
                type="number"
                step="0.5"
                className="w-24 rounded bg-neutral-900 p-2"
                value={draft.reach_cm ?? ""}
                onChange={(e) => set("reach_cm", num(e.target.value))}
              />
              <Lbl>Shoulder (cm)</Lbl>
              <input
                type="number"
                step="0.5"
                className="w-24 rounded bg-neutral-900 p-2"
                value={draft.shoulder_width_cm ?? ""}
                onChange={(e) =>
                  set("shoulder_width_cm", num(e.target.value))
                }
              />
            </Row>
          </Group>

          <Group title="Record">
            <Row>
              <Lbl>Wins</Lbl>
              <input
                type="number"
                min={0}
                className="w-20 rounded bg-neutral-900 p-2"
                value={draft.record_wins}
                onChange={(e) => set("record_wins", Number(e.target.value || 0))}
              />
              <Lbl>Losses</Lbl>
              <input
                type="number"
                min={0}
                className="w-20 rounded bg-neutral-900 p-2"
                value={draft.record_losses}
                onChange={(e) => set("record_losses", Number(e.target.value || 0))}
              />
              <Lbl>Draws</Lbl>
              <input
                type="number"
                min={0}
                className="w-20 rounded bg-neutral-900 p-2"
                value={draft.record_draws}
                onChange={(e) => set("record_draws", Number(e.target.value || 0))}
              />
              <Lbl>KOs</Lbl>
              <input
                type="number"
                min={0}
                className="w-20 rounded bg-neutral-900 p-2"
                value={draft.record_kos}
                onChange={(e) => set("record_kos", Number(e.target.value || 0))}
              />
            </Row>
          </Group>

          <Group title="External IDs">
            <Row>
              <Lbl>BoxRec ID</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2 font-mono"
                value={draft.boxrec_id ?? ""}
                onChange={(e) => set("boxrec_id", e.target.value || null)}
              />
            </Row>
            <Row>
              <Lbl>USA Boxing ID</Lbl>
              <input
                className="flex-1 rounded bg-neutral-900 p-2 font-mono"
                value={draft.usa_boxing_id ?? ""}
                onChange={(e) => set("usa_boxing_id", e.target.value || null)}
              />
            </Row>
          </Group>

          <Group title="Notes">
            <textarea
              className="w-full rounded bg-neutral-900 p-2"
              rows={3}
              value={draft.notes ?? ""}
              onChange={(e) => set("notes", e.target.value || null)}
            />
          </Group>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="rounded border border-neutral-800 p-3">
      <legend className="px-1 text-xs uppercase tracking-wider text-neutral-500">
        {title}
      </legend>
      <div className="mt-2 space-y-2">{children}</div>
    </fieldset>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}

function Lbl({ children }: { children: React.ReactNode }) {
  return <label className="text-xs text-neutral-400">{children}</label>;
}

function labelForSkill(s: SkillLevel): string {
  return s.replace(/_/g, " ");
}

function labelForWeightClass(s: string): string {
  return s.replace(/_/g, " ");
}
