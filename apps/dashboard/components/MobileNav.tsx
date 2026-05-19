"use client";

/**
 * MobileNav — iOS-style bottom tab bar + top title bar.
 * Replaces the sidebar slide-in on screens narrower than md breakpoint.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

function extractFighterId(pathname: string): string | null {
  const m = pathname.match(/^\/fighters\/([^/]+)/);
  return m ? m[1] : null;
}

function pageTitle(pathname: string): string {
  if (pathname === "/") return "Alion";
  if (pathname.startsWith("/admin/users")) return "Users";
  if (pathname.startsWith("/admin/fighters")) return "Fighters";
  if (pathname.startsWith("/admin/coaches")) return "Coaches";
  if (pathname.startsWith("/admin/gyms")) return "Gyms";
  if (pathname.startsWith("/admin")) return "Admin";
  if (pathname.startsWith("/gym-dashboard/members")) return "Members";
  if (pathname.startsWith("/gym-dashboard/coaches")) return "Coaches";
  if (pathname.startsWith("/gym-dashboard/gyms")) return "Gyms";
  if (pathname.startsWith("/gym-dashboard")) return "Gym Dashboard";
  if (pathname.includes("/sessions/")) return "Session";
  if (pathname.includes("/sessions")) return "Sessions";
  if (pathname.includes("/hrv")) return "HRV";
  if (pathname.includes("/observations")) return "Observations";
  if (pathname.includes("/medical")) return "Medical";
  if (pathname.includes("/team")) return "Team";
  if (pathname.includes("/imu")) return "IMU";
  if (pathname.startsWith("/fighters/")) return "Fighter";
  if (pathname.startsWith("/coaches/")) return "Coach";
  if (pathname.startsWith("/profile")) return "Profile";
  if (pathname.startsWith("/compare")) return "Compare";
  return "Alion";
}

interface Props {
  onMenuToggle: () => void;
  menuOpen: boolean;
}

export function MobileTopBar({ onMenuToggle, menuOpen }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const isDeepPage = pathname.split("/").filter(Boolean).length > 1;
  const title = pageTitle(pathname);

  return (
    <div
      className="fixed left-0 right-0 top-0 z-40 flex items-center bg-[#0d0d12]/95 backdrop-blur-md md:hidden"
      style={{ paddingTop: "env(safe-area-inset-top, 0px)", height: "calc(env(safe-area-inset-top, 0px) + 52px)" }}
    >
      <div className="flex w-full items-center px-3" style={{ height: "52px" }}>
        {/* Left: back or spacer */}
        <div className="w-10">
          {isDeepPage && (
            <button
              onClick={() => router.back()}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/8 text-white active:bg-white/15"
              aria-label="Go back"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M11 4L6 9L11 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          )}
        </div>

        {/* Centre: page title */}
        <h1 className="flex-1 text-center text-[15px] font-semibold text-white">{title}</h1>

        {/* Right: hamburger */}
        <div className="w-10 flex justify-end">
          <button
            onClick={onMenuToggle}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/8 text-white active:bg-white/15"
            aria-label="Toggle menu"
          >
            {menuOpen ? (
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M4 4L14 14M14 4L4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M3 5H15M3 9H15M3 13H15" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export function MobileBottomBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();

  const fighterId = extractFighterId(pathname);

  // Build bottom tab items based on context
  type Tab = { label: string; icon: React.ReactNode; href: string };
  const tabs: Tab[] = [];

  const homeHref = (() => {
    if (!user) return "/";
    if (user.role === "fighter" && user.profile_id) return `/fighters/${user.profile_id}`;
    if (user.role === "coach" && user.profile_id) return `/coaches/${user.profile_id}`;
    if (user.role === "gym_manager") return "/gym-dashboard";
    if (user.role === "admin") return "/admin";
    return "/";
  })();

  tabs.push({
    label: "Home",
    icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M3 9.5L11 3L19 9.5V19H14V14H8V19H3V9.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/></svg>,
    href: homeHref,
  });

  if (fighterId) {
    tabs.push({
      label: "Sessions",
      icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.8"/><path d="M11 7V11L14 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
      href: `/fighters/${fighterId}/sessions`,
    });
    tabs.push({
      label: "HRV",
      icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M2 11H5L8 5L11 17L14 8L17 13H20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>,
      href: `/fighters/${fighterId}/hrv`,
    });
  } else if (user?.role === "admin") {
    tabs.push({
      label: "Users",
      icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8"/><path d="M4 19c0-3.866 3.134-7 7-7s7 3.134 7 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
      href: "/admin/users",
    });
    tabs.push({
      label: "Fighters",
      icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.8"/><path d="M2 19c0-3.3 2.7-6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><circle cx="15" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.8"/><path d="M10.5 19c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
      href: "/admin/fighters",
    });
  } else if (user?.role === "gym_manager") {
    tabs.push({
      label: "Members",
      icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.8"/><path d="M2 19c0-3.3 2.7-6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><circle cx="15" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.8"/><path d="M10.5 19c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
      href: "/gym-dashboard/members",
    });
  }

  // New session button for coaches/fighters in fighter context
  const canAddSession = fighterId && user?.role !== "admin" && user?.role !== "gym_manager";

  tabs.push({
    label: "Profile",
    icon: <svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8"/><path d="M4 19c0-3.866 3.134-7 7-7s7 3.134 7 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>,
    href: "/profile",
  });

  const isActive = (href: string) => {
    if (href === homeHref) return pathname === href;
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-white/8 bg-[#0d0d12]/95 backdrop-blur-md md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      <div className="flex items-stretch">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`flex flex-1 flex-col items-center justify-center gap-0.5 py-2.5 transition-colors ${
              isActive(tab.href) ? "text-emerald-400" : "text-neutral-500"
            }`}
          >
            {tab.icon}
            <span className="text-[10px] font-medium">{tab.label}</span>
          </Link>
        ))}

        {canAddSession && (
          <button
            onClick={async () => {
              try {
                const s = await api.createSession(fighterId!, "live_webcam", "mediapipe");
                router.push(`/sessions/${s.id}`);
              } catch { /* ignore */ }
            }}
            className="flex flex-1 flex-col items-center justify-center gap-0.5 py-2.5 text-emerald-400"
          >
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.8"/>
              <path d="M11 7V15M7 11H15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
            <span className="text-[10px] font-medium">Record</span>
          </button>
        )}
      </div>
    </div>
  );
}
