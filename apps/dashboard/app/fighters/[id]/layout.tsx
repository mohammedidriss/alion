"use client";

import { useEffect, useState } from "react";
import { FighterSidebar } from "@/components/FighterSidebar";
import { api, type Fighter } from "@/lib/api";

export default function FighterLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .getFighter(params.id)
      .then(setFighter)
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  if (err) {
    return (
      <main className="p-8 text-sm text-red-400">{err}</main>
    );
  }
  if (!fighter) {
    return (
      <main className="p-8 text-sm text-neutral-400">Loading fighter…</main>
    );
  }

  return (
    <div className="flex">
      <FighterSidebar fighter={fighter} />
      <main className="min-w-0 flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
