"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import type { Fighter } from "@/lib/api";

const TABS = [
  { slug: "", label: "Dashboard", icon: "▦" },
  { slug: "sessions", label: "Sessions", icon: "▷" },
  { slug: "hrv", label: "HRV", icon: "♥" },
  { slug: "imu", label: "IMU", icon: "▤" },
  { slug: "medical", label: "Medical", icon: "✚" },
  { slug: "observations", label: "Observations", icon: "✎" },
] as const;

export function FighterSidebar({ fighter }: { fighter: Fighter }) {
  const pathname = usePathname();
  const base = `/fighters/${fighter.id}`;
  const isActive = (slug: string) => {
    if (slug === "") {
      // Dashboard is active for the bare base, OR /matrix (legacy)
      return pathname === base || pathname === `${base}/matrix`;
    }
    return pathname === `${base}/${slug}` || pathname.startsWith(`${base}/${slug}/`);
  };
  return (
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col gap-4 border-r border-white/5 bg-[#0d0d12] p-4">
      <Link
        href="/"
        className="text-xs text-neutral-400 transition-colors hover:text-neutral-100"
      >
        ← All fighters
      </Link>

      <div className="flex flex-col items-center gap-2 py-2">
        <ProfileAvatar
          name={fighter.name}
          photo_path={fighter.photo_path}
          size={96}
        />
        <div className="text-center">
          <div className="text-base font-semibold leading-tight">
            {fighter.name}
          </div>
          {fighter.nickname && (
            <div className="text-xs text-neutral-400">
              &ldquo;{fighter.nickname}&rdquo;
            </div>
          )}
          <div className="mt-0.5 text-xs text-neutral-500">
            {fighter.stance}
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        {TABS.map((t) => (
          <Link
            key={t.slug}
            href={t.slug ? `${base}/${t.slug}` : base}
            className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors ${
              isActive(t.slug)
                ? "bg-white/10 text-white"
                : "text-neutral-400 hover:bg-white/5 hover:text-neutral-100"
            }`}
          >
            <span className="w-4 text-center" aria-hidden>
              {t.icon}
            </span>
            <span>{t.label}</span>
          </Link>
        ))}
      </nav>

      <div className="mt-auto pt-4">
        <Link
          href={`/sessions/new?fighter=${fighter.id}`}
          className="flex w-full items-center justify-center rounded-xl bg-emerald-500 px-3 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          + New session
        </Link>
      </div>
    </aside>
  );
}

