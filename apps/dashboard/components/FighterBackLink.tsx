"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Fighter } from "@/lib/api";

interface Props {
  fighterId: string;
  /** Optional className passthrough so callers can tweak spacing. */
  className?: string;
}

/**
 * Back-link with the fighter's name and avatar.
 *
 * Replaces the generic "Back to fighter" link on every page that's
 * scoped to a single fighter (sessions, matrix, etc.). Fetches the
 * fighter row on mount and shows their photo + name; falls back to
 * "Back to fighter" while loading or if the lookup errors.
 */
export function FighterBackLink({ fighterId, className }: Props) {
  const [fighter, setFighter] = useState<Fighter | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getFighter(fighterId)
      .then((f) => {
        if (!cancelled) setFighter(f);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [fighterId]);

  const photo = api.photoUrl(fighter?.photo_path ?? null);
  return (
    <Link
      href={`/fighters/${fighterId}`}
      className={`inline-flex items-center gap-2 text-sm text-neutral-400 hover:text-neutral-100 ${className ?? ""}`}
    >
      <span aria-hidden>←</span>
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={photo}
          alt=""
          className="h-7 w-7 rounded-full border border-white/10 object-cover"
        />
      ) : (
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-neutral-800 text-[10px] uppercase text-neutral-400">
          {fighter?.name?.[0] ?? "?"}
        </span>
      )}
      <span>Back to {fighter?.name ?? "fighter"}</span>
    </Link>
  );
}
