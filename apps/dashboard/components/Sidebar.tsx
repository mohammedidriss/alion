"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AlionWordmark } from "@/components/AlionLogo";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { canStartSession, fighterTabsFor, navSections, type NavItem } from "@/lib/nav";

/** Extract fighter ID from pathname like /fighters/abc-123/sessions */
function extractFighterId(pathname: string): string | null {
  const m = pathname.match(/^\/fighters\/([^/]+)/);
  return m ? m[1] : null;
}

/** Extract coach ID from pathname like /coaches/abc-123 */
function extractCoachId(pathname: string): string | null {
  const m = pathname.match(/^\/coaches\/([^/]+)/);
  return m ? m[1] : null;
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  const fighterId = extractFighterId(pathname);
  const coachId = extractCoachId(pathname);

  // The menu comes from what this account may do (lib/nav.ts, ADR-046).
  const sections = navSections(user);
  const fighterTabs: NavItem[] = fighterId
    ? fighterTabsFor(user).map((t) => ({
        label: t.label,
        href: t.slug ? `/fighters/${fighterId}/${t.slug}` : `/fighters/${fighterId}`,
        icon: t.icon,
        hint: t.hint,
      }))
    : [];

  // Coach context
  const coachTabs: NavItem[] = coachId
    ? [{ label: "Coach Profile", href: `/coaches/${coachId}`, icon: "P" }]
    : [];

  const isTabActive = (href: string, isExact?: boolean) => {
    if (href === "/") return pathname === "/";
    if (isExact) return pathname === href;
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-white/5 bg-[#0d0d12]">
      {/* Logo */}
      <div className="px-4 pt-5 pb-4">
        <Link href="/">
          <AlionWordmark size={28} />
        </Link>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2">
        {/* Global nav, by section */}
        {sections.map((sec) => (
          <div key={sec.title ?? "mine"} className={sec.title ? "pt-3" : ""}>
            {sec.title && (
              <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-neutral-600">
                {sec.title}
              </div>
            )}
            {sec.items.map((item) => (
              <Link
                key={item.href + item.label}
                href={item.href}
                title={item.hint}
                onClick={onNavigate}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isTabActive(item.href)
                    ? "bg-white/[0.08] text-white font-medium"
                    : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
                }`}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded text-[11px] bg-white/[0.06]">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            ))}
          </div>
        ))}

        {/* Fighter context section */}
        {fighterTabs.length > 0 && (
          <>
            <div className="mt-4 mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-neutral-600">
              Fighter
            </div>
            {fighterTabs.map((t) => {
              // Dashboard tab: exact match only
              const active =
                t.href === `/fighters/${fighterId}`
                  ? pathname === t.href || pathname === `${t.href}/matrix`
                  : isTabActive(t.href);
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  title={t.hint}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-white/10 text-white font-medium"
                      : "text-neutral-400 hover:bg-white/5 hover:text-neutral-100"
                  }`}
                >
                  <span className="w-4 text-center text-xs" aria-hidden>
                    {t.icon}
                  </span>
                  {t.label}
                </Link>
              );
            })}

            {/* Training session button: coaches and researchers */}
            {canStartSession(user) && (
              <button
                onClick={async (e) => {
                  const btn = e.currentTarget;
                  btn.disabled = true;
                  try {
                    const s = await api.createSession(fighterId!, "live_webcam", "mediapipe");
                    router.push(`/sessions/${s.id}`);
                  } catch {
                    btn.disabled = false;
                  }
                }}
                className="mt-2 flex w-full items-center justify-center rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-black hover:bg-emerald-400 disabled:opacity-50"
              >
                + Training session
              </button>
            )}
          </>
        )}

        {/* Coach context section */}
        {coachTabs.length > 0 && (
          <>
            <div className="mt-4 mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-neutral-600">
              Coach
            </div>
            {coachTabs.map((t) => (
              <Link
                key={t.href}
                href={t.href}
                title={t.hint}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isTabActive(t.href)
                    ? "bg-white/10 text-white font-medium"
                    : "text-neutral-400 hover:bg-white/5 hover:text-neutral-100"
                }`}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded text-[11px] bg-white/[0.06]">
                  {t.icon}
                </span>
                {t.label}
              </Link>
            ))}
          </>
        )}
      </nav>

      {/* Profile footer */}
      <div className="border-t border-white/5 p-3">
        {user ? (
          <div className="flex items-center gap-2">
            <Link href="/profile" className="flex items-center gap-2 min-w-0 flex-1 rounded-lg px-1 py-0.5 -ml-1 hover:bg-white/[0.05] transition-colors" title="Edit profile">
              <ProfileAvatar name={user.name} photo_path={user.photo_path} size={32} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{user.name}</p>
                <p className="truncate text-[10px] capitalize text-neutral-500">
                  {user.role === "gym_manager" ? "gym manager" : user.role}
                  {user.is_researcher && " · researcher"}
                </p>
              </div>
            </Link>
            <button
              onClick={() => { logout(); router.push("/"); }}
              className="text-[10px] text-neutral-600 hover:text-neutral-300"
              title="Sign out"
            >
              Log out
            </button>
          </div>
        ) : (
          <p className="text-[11px] text-neutral-600">Not signed in</p>
        )}
      </div>
    </aside>
  );
}
