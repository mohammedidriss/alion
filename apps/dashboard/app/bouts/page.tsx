"use client";

/**
 * Fights (ADR-011, ADR-069) — two-fighter fights. A *training* session has one
 * fighter (the fighter's Training sessions page); a *fight* links two, one per
 * corner. Starting a fight sets its card the way a broadcast presents it: the kind
 * of fight and any belts on the line, the two fighters' tale of the tape (missing
 * facts can be filled in here and are saved to their profiles), the event and
 * arena, the division and weigh-ins, the rounds, the officials and the promotion.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TaleOfTheTape } from "@/components/TaleOfTheTape";
import {
  api,
  type BeltOnTheLine,
  type Bout,
  type FightOptions,
  type FightType,
  type Fighter,
  type FighterTitle,
} from "@/lib/api";
import { TITLE_KIND_LABEL, kgLb, weightClassLabel, whatsAtStake } from "@/lib/fight";

const CATCHWEIGHT = "__catchweight";
const field =
  "w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-500";

function localNow(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function BoutsPage() {
  const router = useRouter();
  const [bouts, setBouts] = useState<Bout[]>([]);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [opts, setOpts] = useState<FightOptions | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [creating, setCreating] = useState(false);

  // The card.
  const [fightType, setFightType] = useState<FightType>("pro");
  const [belts, setBelts] = useState<BeltOnTheLine[]>([]);
  const [redId, setRedId] = useState("");
  const [blueId, setBlueId] = useState("");
  const [titles, setTitles] = useState<Record<string, FighterTitle[]>>({});
  const [weighIn, setWeighIn] = useState<{ red: number | null; blue: number | null }>({
    red: null,
    blue: null,
  });
  const [eventName, setEventName] = useState("");
  const [when, setWhen] = useState(localNow());
  const [venue, setVenue] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [division, setDivision] = useState("");
  const [catchKg, setCatchKg] = useState("");
  const [rounds, setRounds] = useState(8);
  const [roundS, setRoundS] = useState(180);
  const [restS, setRestS] = useState(60);
  const [referee, setReferee] = useState("");
  const [judges, setJudges] = useState(["", "", ""]);
  const [promoter, setPromoter] = useState("");
  const [broadcaster, setBroadcaster] = useState("");
  const [label, setLabel] = useState("");

  useEffect(() => {
    api.listBouts().then(setBouts).catch((e) => setErr(String(e)));
    api.listFighters().then(setFighters).catch(() => {});
    api.fightOptions().then(setOpts).catch(() => {});
  }, []);

  const red = fighters.find((f) => f.id === redId) ?? null;
  const blue = fighters.find((f) => f.id === blueId) ?? null;

  useEffect(() => {
    for (const id of [redId, blueId]) {
      if (id && !titles[id]) {
        api
          .listTitles(id)
          .then((ts) => setTitles((m) => ({ ...m, [id]: ts })))
          .catch(() => setTitles((m) => ({ ...m, [id]: [] })));
      }
    }
  }, [redId, blueId, titles]);

  const chooseType = (t: FightType) => {
    setFightType(t);
    const d = opts?.fight_types.find((x) => x.key === t);
    if (d) {
      setRounds(d.rounds);
      setRoundS(d.round_s);
      setRestS(d.rest_s);
    }
    if (t !== "pro_title") setBelts([]);
  };

  const limitKg = useMemo(() => {
    if (division === CATCHWEIGHT) {
      const v = Number.parseFloat(catchKg);
      return Number.isFinite(v) && v > 0 ? v : null;
    }
    return opts?.weight_classes.find((w) => w.key === division)?.limit_kg ?? null;
  }, [division, catchKg, opts]);

  const problems: string[] = [];
  if (!redId || !blueId) problems.push("Pick a fighter for each corner");
  else if (redId === blueId) problems.push("The two corners need different fighters");
  if (fightType === "pro_title" && belts.length === 0) problems.push("Pick the belt(s) on the line");
  if (division === CATCHWEIGHT && limitKg == null) problems.push("Enter the catchweight limit");

  const create = async () => {
    if (problems.length || creating) return;
    setCreating(true);
    setErr(null);
    try {
      const bout = await api.createBout({
        label: label.trim() || `${red?.name ?? "Red"} v ${blue?.name ?? "Blue"}`,
        fight_type: fightType,
        titles: belts,
        event_name: eventName.trim() || null,
        scheduled_at: when ? new Date(when).toISOString() : null,
        venue: venue.trim() || null,
        city: city.trim() || null,
        country: country.trim() || null,
        weight_class: division && division !== CATCHWEIGHT ? division : null,
        weight_limit_kg: division === CATCHWEIGHT ? limitKg : null,
        red_weigh_in_kg: weighIn.red,
        blue_weigh_in_kg: weighIn.blue,
        referee: referee.trim() || null,
        judges: judges.map((j) => j.trim()).filter(Boolean),
        promoter: promoter.trim() || null,
        broadcaster: broadcaster.trim() || null,
        round_count: rounds,
        round_duration_s: roundS,
        rest_duration_s: restS,
      });
      // One single-fighter session per corner, linked to the fight.
      const redSession = await api.createSession(redId, "live_webcam");
      await api.assignBoutCorner(bout.id, redSession.id, "red");
      const blueSession = await api.createSession(blueId, "live_webcam");
      await api.assignBoutCorner(bout.id, blueSession.id, "blue");
      router.push(`/bouts/${bout.id}`);
    } catch (e) {
      setErr(String(e));
      setCreating(false);
    }
  };

  const remove = async (b: Bout) => {
    if (
      !window.confirm(
        `Delete "${b.label || "this fight"}"? It's hidden from everyone, with both corners' sessions; anything recorded is kept.`,
      )
    )
      return;
    try {
      await api.deleteBout(b.id);
      setBouts((list) => list.filter((x) => x.id !== b.id));
    } catch (e) {
      setErr(String(e));
    }
  };

  const savedFighter = (f: Fighter) => setFighters((list) => list.map((x) => (x.id === f.id ? f : x)));

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Fights</h1>
          <p className="text-sm text-neutral-400">
            Two-fighter fights. For a single fighter, start a training session from the
            fighter&apos;s Training sessions page.
          </p>
        </div>
        <button
          onClick={() => setShowNew((s) => !s)}
          className="shrink-0 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          {showNew ? "Cancel" : "+ Start fight"}
        </button>
      </header>

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>
      )}

      {showNew && (
        <div className="card space-y-6">
          <h2 className="text-lg font-semibold">Start a fight</h2>

          {/* 1. What kind of fight */}
          <Section title="Fight">
            <div className="flex flex-wrap gap-2">
              {(opts?.fight_types ?? []).map((t) => (
                <button
                  key={t.key}
                  onClick={() => chooseType(t.key)}
                  className={`rounded-full border px-3 py-1.5 text-sm ${
                    fightType === t.key
                      ? "border-emerald-400 bg-emerald-500/15 text-emerald-200"
                      : "border-white/10 text-neutral-300 hover:bg-white/5"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {fightType === "pro_title" && opts && (
              <BeltPicker
                bodies={opts.sanctioning_bodies}
                kinds={opts.title_kinds}
                value={belts}
                onChange={setBelts}
              />
            )}
          </Section>

          {/* 2. The fighters */}
          <Section title="Fighters">
            <div className="grid gap-3 sm:grid-cols-2">
              <CornerPicker corner="red" fighters={fighters} value={redId} exclude={blueId} onChange={setRedId} />
              <CornerPicker corner="blue" fighters={fighters} value={blueId} exclude={redId} onChange={setBlueId} />
            </div>
            {(red || blue) && (
              <>
                <TaleOfTheTape
                  red={red}
                  blue={blue}
                  redTitles={titles[redId] ?? []}
                  blueTitles={titles[blueId] ?? []}
                  weighIn={weighIn}
                  limitKg={limitKg}
                  onWeighIn={(c, kg) => setWeighIn((w) => ({ ...w, [c]: kg }))}
                  onFighterSaved={savedFighter}
                />
                <p className="text-xs text-neutral-500">
                  Click any value to fill it in or correct it — it&apos;s saved to the fighter&apos;s
                  profile. The weigh-in belongs to this fight; add it now or on the fight&apos;s page.
                </p>
              </>
            )}
          </Section>

          {/* 3. Where and when */}
          <Section title="Event">
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={eventName} onChange={(e) => setEventName(e.target.value)} placeholder="Event name — e.g. Fight Night 12" className={field} />
              <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className={field} />
              <input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="Arena / venue" className={field} />
              <div className="grid grid-cols-2 gap-3">
                <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="City" className={field} />
                <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Country" className={field} />
              </div>
            </div>
          </Section>

          {/* 4. Weight */}
          <Section title="Weight">
            <div className="grid gap-3 sm:grid-cols-2">
              <select value={division} onChange={(e) => setDivision(e.target.value)} className={field}>
                <option value="">Division…</option>
                {(opts?.weight_classes ?? []).map((w) => (
                  <option key={w.key} value={w.key}>
                    {weightClassLabel(w.key)}
                    {w.limit_lb ? ` — ${w.limit_lb} lb / ${w.limit_kg} kg` : " — no limit"}
                  </option>
                ))}
                <option value={CATCHWEIGHT}>Catchweight (agreed limit)…</option>
              </select>
              {division === CATCHWEIGHT ? (
                <input type="number" step="0.1" value={catchKg} onChange={(e) => setCatchKg(e.target.value)} placeholder="Limit in kg" className={field} />
              ) : (
                <div className="self-center text-sm text-neutral-400">
                  {limitKg ? `Limit ${kgLb(limitKg)}` : division ? "No upper limit" : ""}
                </div>
              )}
            </div>
          </Section>

          {/* 5. Rounds */}
          <Section title="Rounds">
            <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-300">
              <label className="flex items-center gap-2">
                <input type="number" min={1} max={24} value={rounds} onChange={(e) => setRounds(Number(e.target.value) || 1)} className={`${field} w-20`} />
                rounds of
              </label>
              <select value={roundS} onChange={(e) => setRoundS(Number(e.target.value))} className={`${field} w-28`}>
                {[60, 90, 120, 180].map((s) => (
                  <option key={s} value={s}>{s / 60} min</option>
                ))}
              </select>
              <label className="flex items-center gap-2">
                rest
                <select value={restS} onChange={(e) => setRestS(Number(e.target.value))} className={`${field} w-24`}>
                  {[30, 45, 60, 90].map((s) => (
                    <option key={s} value={s}>{s} s</option>
                  ))}
                </select>
              </label>
            </div>
          </Section>

          {/* 6. Officials and promotion */}
          <Section title="Officials">
            <div className="grid gap-3 sm:grid-cols-4">
              <input value={referee} onChange={(e) => setReferee(e.target.value)} placeholder="Referee" className={field} />
              {judges.map((j, i) => (
                <input
                  key={i}
                  value={j}
                  onChange={(e) => setJudges((js) => js.map((x, k) => (k === i ? e.target.value : x)))}
                  placeholder={`Judge ${i + 1}`}
                  className={field}
                />
              ))}
            </div>
          </Section>
          <Section title="Promotion">
            <div className="grid gap-3 sm:grid-cols-3">
              <input value={promoter} onChange={(e) => setPromoter(e.target.value)} placeholder="Promoter" className={field} />
              <input value={broadcaster} onChange={(e) => setBroadcaster(e.target.value)} placeholder="Broadcaster" className={field} />
              <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={`Name — ${red?.name ?? "Red"} v ${blue?.name ?? "Blue"}`} className={field} />
            </div>
          </Section>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={create}
              disabled={problems.length > 0 || creating}
              className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
            >
              {creating ? "Starting…" : "Start fight"}
            </button>
            {problems.length > 0 && <span className="text-xs text-amber-300">{problems[0]}</span>}
          </div>
        </div>
      )}

      {bouts.length === 0 ? (
        <p className="text-sm text-neutral-500">No fights yet — start one to record it.</p>
      ) : (
        <ul className="space-y-3">
          {bouts.map((b) => (
            <li key={b.id} className="card flex items-center justify-between gap-3 transition-colors hover:border-white/15">
              <Link href={`/bouts/${b.id}`} className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{b.label || "Untitled fight"}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      b.fight_type === "pro_title" ? "bg-amber-500/15 text-amber-200" : "bg-white/5 text-neutral-300"
                    }`}
                  >
                    {whatsAtStake(b)}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-xs text-neutral-400">
                  {[b.event_name, b.venue, [b.city, b.country].filter(Boolean).join(", ")].filter(Boolean).join(" · ")}
                  {b.event_name || b.venue || b.city ? " · " : ""}
                  {new Date(b.scheduled_at).toLocaleString()} · {b.round_count}×{b.round_duration_s / 60} min
                  {b.weight_class ? ` · ${weightClassLabel(b.weight_class)}` : b.weight_limit_kg ? ` · ${b.weight_limit_kg} kg catchweight` : ""}
                </div>
              </Link>
              {b.winner_corner ? (
                <span className={b.winner_corner === "red" ? "text-sm text-red-400" : b.winner_corner === "blue" ? "text-sm text-sky-400" : "text-sm text-neutral-300"}>
                  {b.winner_corner === "draw" ? "Draw" : `${b.winner_corner} won`}
                  {b.result_method ? ` · ${b.result_method}` : ""}
                </span>
              ) : (
                <Link href={`/bouts/${b.id}`} className="text-sm text-neutral-500">open →</Link>
              )}
              <button
                onClick={() => remove(b)}
                className="rounded-lg px-2 py-1 text-xs text-red-400/70 hover:bg-red-500/10 hover:text-red-300"
                title="Delete the fight — recordings are kept"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">{title}</h3>
      {children}
    </section>
  );
}

function BeltPicker({
  bodies,
  kinds,
  value,
  onChange,
}: {
  bodies: string[];
  kinds: string[];
  value: BeltOnTheLine[];
  onChange: (v: BeltOnTheLine[]) => void;
}) {
  const on = (body: string) => value.find((t) => t.body === body);
  const toggle = (body: string) =>
    onChange(
      on(body)
        ? value.filter((t) => t.body !== body)
        : [...value, { body, kind: body === "Regional" ? "regional" : body === "Other" ? "other" : "world" }],
    );
  return (
    <div className="space-y-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3">
      <div className="text-xs text-amber-200/80">Belts on the line — pick every one at stake</div>
      <div className="flex flex-wrap gap-2">
        {bodies.map((b) => {
          const sel = on(b);
          return (
            <div key={b} className={`flex items-center gap-1 rounded-full border px-1 py-0.5 ${sel ? "border-amber-400/60 bg-amber-500/10" : "border-white/10"}`}>
              <button onClick={() => toggle(b)} className={`rounded-full px-2 py-1 text-sm ${sel ? "text-amber-100" : "text-neutral-300"}`}>
                {sel ? "✓ " : ""}
                {b}
              </button>
              {sel && (
                <select
                  value={sel.kind}
                  onChange={(e) => onChange(value.map((t) => (t.body === b ? { ...t, kind: e.target.value } : t)))}
                  className="rounded-md border border-white/10 bg-black/40 px-1.5 py-0.5 text-xs text-neutral-200"
                >
                  {kinds.map((k) => (
                    <option key={k} value={k}>{TITLE_KIND_LABEL[k] ?? k}</option>
                  ))}
                </select>
              )}
            </div>
          );
        })}
      </div>
      {value.length > 1 && <div className="text-xs text-amber-200/70">Unification bout — {value.length} belts.</div>}
    </div>
  );
}

function CornerPicker({
  corner,
  fighters,
  value,
  exclude,
  onChange,
}: {
  corner: "red" | "blue";
  fighters: Fighter[];
  value: string;
  exclude: string;
  onChange: (id: string) => void;
}) {
  const tint =
    corner === "red"
      ? "border-red-500/40 bg-red-500/[0.05] text-red-300"
      : "border-sky-500/40 bg-sky-500/[0.05] text-sky-300";
  return (
    <div className={`rounded-xl border p-3 ${tint}`}>
      <div className="mb-2 text-xs font-semibold uppercase">{corner} corner</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-neutral-100"
      >
        <option value="">Select fighter…</option>
        {fighters
          .filter((f) => f.id !== exclude)
          .map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
              {f.record_wins + f.record_losses + f.record_draws > 0
                ? ` (${f.record_wins}-${f.record_losses}-${f.record_draws})`
                : ""}
            </option>
          ))}
      </select>
    </div>
  );
}
