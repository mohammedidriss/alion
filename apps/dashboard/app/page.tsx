"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CreateProfileModal } from "@/components/CreateProfileModal";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type Fighter,
  type Referee,
} from "@/lib/api";
import { type ProfileKind, useActiveProfile } from "@/lib/activeProfile";

interface FighterRow {
  fighter: Fighter;
  sessionCount: number;
  lastSessionAt: string | null;
}

export default function Home() {
  const [health, setHealth] = useState<{ status: string; schema_version: string } | null>(
    null,
  );
  const [fighters, setFighters] = useState<FighterRow[]>([]);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [referees, setReferees] = useState<Referee[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState<ProfileKind | null>(null);
  const { active, setActive } = useActiveProfile();

  const load = useCallback(async () => {
    try {
      const [hRes, fs, cs, rs, allSessions] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        api.listFighters(),
        api.listCoaches(),
        api.listReferees(),
        api.listSessions(),
      ]);
      setHealth(hRes);
      setCoaches(cs);
      setReferees(rs);
      const counts = new Map<string, { n: number; last: string | null }>();
      for (const s of allSessions) {
        const cur = counts.get(s.fighter_id) ?? { n: 0, last: null };
        cur.n += 1;
        if (!cur.last || s.started_at > cur.last) cur.last = s.started_at;
        counts.set(s.fighter_id, cur);
      }
      const out: FighterRow[] = fs.map((f) => {
        const c = counts.get(f.id) ?? { n: 0, last: null };
        return { fighter: f, sessionCount: c.n, lastSessionAt: c.last };
      });
      out.sort((a, b) => (b.lastSessionAt ?? "").localeCompare(a.lastSessionAt ?? ""));
      setFighters(out);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onCreated = (kind: ProfileKind) =>
    (id: string, name: string, photo_path: string | null) => {
      setCreating(null);
      setActive({ kind, id, name, photo_path });
      load();
    };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-8 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Roster</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Sign in as an existing profile or create a new one.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {active ? (
            <ActingAsBadge
              kind={active.kind}
              name={active.name}
              photo_path={active.photo_path}
              onSwitch={() => setActive(null)}
            />
          ) : (
            <span className="pill bg-neutral-700/40 text-neutral-300">
              not signed in
            </span>
          )}
          {health ? (
            <span className="pill bg-emerald-500/15 text-emerald-300">
              ● API healthy · schema {health.schema_version}
            </span>
          ) : (
            <span className="pill bg-amber-500/15 text-amber-300">
              ● API unreachable
            </span>
          )}
        </div>
      </header>

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      <Section
        title="Fighters"
        kind="fighter"
        count={fighters.length}
        onCreate={() => setCreating("fighter")}
      >
        {fighters.length === 0 ? (
          <Empty
            label="No fighters yet"
            cta="Create the first fighter profile to get started."
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {fighters.map(({ fighter: f, sessionCount, lastSessionAt }) => (
              <li key={f.id}>
                <ProfileCard
                  href={`/fighters/${f.id}`}
                  name={f.name}
                  nickname={f.nickname}
                  photo_path={f.photo_path}
                  active={active?.kind === "fighter" && active.id === f.id}
                  onSignIn={() =>
                    setActive({
                      kind: "fighter",
                      id: f.id,
                      name: f.name,
                      photo_path: f.photo_path,
                    })
                  }
                  meta={[
                    f.stance,
                    `${sessionCount} session${sessionCount === 1 ? "" : "s"}`,
                    lastSessionAt
                      ? `last ${new Date(lastSessionAt).toLocaleDateString()}`
                      : "no sessions",
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Coaches"
        kind="coach"
        count={coaches.length}
        onCreate={() => setCreating("coach")}
      >
        {coaches.length === 0 ? (
          <Empty
            label="No coaches yet"
            cta="Coaches add observations and track fighter progress."
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {coaches.map((c) => (
              <li key={c.id}>
                <ProfileCard
                  href={`/coaches/${c.id}`}
                  name={c.name}
                  nickname={null}
                  photo_path={c.photo_path}
                  active={active?.kind === "coach" && active.id === c.id}
                  onSignIn={() =>
                    setActive({
                      kind: "coach",
                      id: c.id,
                      name: c.name,
                      photo_path: c.photo_path,
                    })
                  }
                  meta={[
                    c.gym ?? "no gym set",
                    c.specialties ?? "no specialties",
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Referees"
        kind="referee"
        count={referees.length}
        onCreate={() => setCreating("referee")}
      >
        {referees.length === 0 ? (
          <Empty
            label="No referees yet"
            cta="Sanctioned officials who oversee bouts."
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {referees.map((r) => (
              <li key={r.id}>
                <ProfileCard
                  href={`/referees/${r.id}`}
                  name={r.name}
                  nickname={null}
                  photo_path={r.photo_path}
                  active={active?.kind === "referee" && active.id === r.id}
                  onSignIn={() =>
                    setActive({
                      kind: "referee",
                      id: r.id,
                      name: r.name,
                      photo_path: r.photo_path,
                    })
                  }
                  meta={[
                    r.sanctioning_body ?? "no sanctioning body",
                    r.license_number ? `lic #${r.license_number}` : "no license",
                  ]}
                />
              </li>
            ))}
          </ul>
        )}
      </Section>

      {creating && (
        <CreateProfileModal
          kind={creating}
          onClose={() => setCreating(null)}
          onCreated={onCreated(creating)}
        />
      )}
    </div>
  );
}

function Section({
  title,
  kind,
  count,
  onCreate,
  children,
}: {
  title: string;
  kind: ProfileKind;
  count: number;
  onCreate: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="card">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-xs text-neutral-500">
            {count} on roster
          </p>
        </div>
        <button
          onClick={onCreate}
          className="rounded-xl bg-emerald-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-emerald-400"
        >
          + Create {kind}
        </button>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function ProfileCard({
  href,
  name,
  nickname,
  photo_path,
  meta,
  active,
  onSignIn,
}: {
  href: string;
  name: string;
  nickname: string | null;
  photo_path: string | null;
  meta: string[];
  active: boolean;
  onSignIn: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border p-3 transition-colors ${
        active
          ? "border-emerald-500/40 bg-emerald-500/5"
          : "border-white/5 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]"
      }`}
    >
      <Link href={href} className="flex min-w-0 flex-1 items-center gap-3">
        <ProfileAvatar name={name} photo_path={photo_path} size={48} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate font-medium">{name}</span>
            {nickname && (
              <span className="truncate text-xs text-neutral-500">
                &ldquo;{nickname}&rdquo;
              </span>
            )}
          </div>
          <div className="truncate text-xs text-neutral-500">
            {meta.filter(Boolean).join(" · ")}
          </div>
        </div>
      </Link>
      <button
        onClick={onSignIn}
        title={active ? "Currently signed in" : "Sign in as this profile"}
        className={`rounded-lg px-2.5 py-1 text-xs ${
          active
            ? "bg-emerald-500/15 text-emerald-300"
            : "bg-white/[0.05] text-neutral-300 hover:bg-white/[0.1]"
        }`}
      >
        {active ? "active" : "sign in"}
      </button>
    </div>
  );
}

function Empty({ label, cta }: { label: string; cta: string }) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center">
      <p className="text-sm font-medium text-neutral-300">{label}</p>
      <p className="mt-1 text-xs text-neutral-500">{cta}</p>
    </div>
  );
}

function ActingAsBadge({
  kind,
  name,
  photo_path,
  onSwitch,
}: {
  kind: ProfileKind;
  name: string;
  photo_path: string | null;
  onSwitch: () => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] py-1 pl-1 pr-3 text-sm">
      <ProfileAvatar name={name} photo_path={photo_path} size={28} />
      <div className="leading-tight">
        <div className="text-[10px] uppercase tracking-wide text-neutral-500">
          {kind}
        </div>
        <div className="text-xs font-medium">{name}</div>
      </div>
      <button
        onClick={onSwitch}
        className="ml-2 text-xs text-neutral-400 hover:text-neutral-100"
        title="Sign out / switch profile"
      >
        switch
      </button>
    </div>
  );
}
