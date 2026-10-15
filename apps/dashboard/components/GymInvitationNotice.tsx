"use client";

/** A gym is waiting for the fighter's answer: a one-line pointer to the profile
 * page, where they answer it (ADR-035) — the dashboard changes nothing itself. */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function GymInvitationNotice() {
  const [n, setN] = useState(0);
  useEffect(() => {
    api
      .gymInvitations()
      .then((i) => setN(i.length))
      .catch(() => setN(0));
  }, []);
  if (n === 0) return null;
  return (
    <Link
      href="/profile"
      className="block rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-2.5 text-sm text-amber-200 hover:bg-amber-950/30"
    >
      {n === 1 ? "A gym wants to add you" : `${n} gyms want to add you`} — answer on your profile page →
    </Link>
  );
}
