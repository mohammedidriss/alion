/**
 * The menu, from what each account may do (ADR-046) — one place, for the sidebar
 * and the phone's bars, so a tab is never missing for someone who may use it and
 * never shown to someone who may not. The API enforces the same rules.
 *
 * - Researcher (ALION_RESEARCHERS): every section — their own training if they are
 *   a fighter, all fighters, research, and administration.
 * - Admin: administration; fighters' profiles, not their training.
 * - Fighter, coach, physician, referee, gym manager: their own work.
 * Model training and model details are for researchers and admins only.
 */

import type { AuthUser } from "@/lib/api";

export type NavItem = { label: string; href: string; icon: string; hint?: string };
export type NavSection = { title: string | null; items: NavItem[] };

export function isAdmin(user: AuthUser | null | undefined): boolean {
  return !!user && (user.role === "admin" || user.is_researcher);
}

/** Model training, model versions and accuracy, detector tools: researchers and admins. */
export function seesModels(user: AuthUser | null | undefined): boolean {
  return isAdmin(user);
}

/** Owns or manages a gym: a gym manager account, or that role at a gym (ADR-052). */
export function managesGym(user: AuthUser | null | undefined): boolean {
  return (
    !!user &&
    (user.role === "gym_manager" || (user.gym_roles ?? []).some((r) => r.role === "owner" || r.role === "manager"))
  );
}

export function homeHref(user: AuthUser | null | undefined): string {
  if (!user) return "/";
  if (user.role === "fighter" && user.profile_id) return `/fighters/${user.profile_id}`;
  if (user.role === "coach" && user.profile_id) return `/coaches/${user.profile_id}`;
  if (user.role === "referee" && user.profile_id) return `/referees/${user.profile_id}`;
  if (user.role === "physician") return "/physician";
  if (user.role === "gym_manager") return "/gym-dashboard";
  if (user.role === "admin" || user.is_researcher) return "/admin";
  return "/";
}

export function navSections(user: AuthUser | null | undefined): NavSection[] {
  if (!user) return [];
  const role = user.role;
  const researcher = user.is_researcher;
  const admin = isAdmin(user);
  const sections: NavSection[] = [];

  const mine: NavItem[] = [{ label: "Home", href: homeHref(user), icon: "H" }];
  if (role === "physician") mine.push({ label: "My fighters", href: "/physician", icon: "✚", hint: "The fighters who chose you as their physician" });
  if (managesGym(user)) {
    if (role !== "gym_manager") mine.push({ label: "My gym", href: "/gym-dashboard", icon: "⌂" });
    mine.push({ label: "Members", href: "/gym-dashboard/members", icon: "◉" });
    mine.push({ label: "Staff", href: "/gym-dashboard/coaches", icon: "◈", hint: "Owners, managers, head coaches and coaches" });
    mine.push({ label: "Gyms", href: "/gym-dashboard/gyms", icon: "⌂" });
  }
  if (["fighter", "coach", "referee", "gym_manager"].includes(role) || researcher) {
    mine.push({ label: "Fights", href: "/bouts", icon: "⚔", hint: "Two-fighter bouts: both corners recorded together" });
  }
  if (!researcher && (user.is_reviewer || user.is_rq1_rater)) {
    mine.push({ label: "Study", href: "/study", icon: "◎", hint: "The study you take part in" });
  }
  mine.push({ label: "Privacy & consent", href: "/privacy", icon: "◐", hint: "What Alion keeps about you, who can see it, and your requests" });
  sections.push({ title: null, items: mine });

  if (researcher) {
    sections.push({
      title: "Research",
      items: [
        { label: "All fighters", href: "/admin/fighters", icon: "⊕", hint: "Every fighter, every tab" },
        { label: "Research datasets", href: "/datasets", icon: "▤", hint: "Recordings and model training" },
        { label: "Study", href: "/study", icon: "◎", hint: "The advisory review study and RQ1 raters" },
        { label: "AI model", href: "/ai-model", icon: "✦", hint: "Which computer writes the AI training advice" },
        { label: "Compare backends", href: "/compare", icon: "C", hint: "Pose and detector backends side by side" },
      ],
    });
  }
  if (admin) {
    const items: NavItem[] = [
      // Home is the overview for a plain admin; a researcher's home is their own page.
      ...(homeHref(user) === "/admin" ? [] : [{ label: "Overview", href: "/admin", icon: "⚙" }]),
      { label: "Users", href: "/admin/users", icon: "◉" },
      { label: "Coaches", href: "/admin/coaches", icon: "◈" },
      { label: "Gym managers", href: "/admin/gym-managers", icon: "M" },
      { label: "Gyms", href: "/admin/gyms", icon: "⌂" },
      { label: "Data requests", href: "/privacy/requests", icon: "✉", hint: "People's requests for a copy, a deletion or to leave the research" },
    ];
    if (!researcher) {
      items.splice(2, 0, { label: "Fighters", href: "/admin/fighters", icon: "⊕" });
      items.push({ label: "AI model", href: "/ai-model", icon: "✦" });
    }
    sections.push({ title: "Administration", items });
  }
  return sections;
}

export const FIGHTER_TABS: { slug: string; label: string; icon: string; hint: string }[] = [
  { slug: "", label: "Dashboard", icon: "▦", hint: "This fighter at a glance" },
  { slug: "sessions", label: "Training sessions", icon: "▷", hint: "Every recorded training session" },
  { slug: "hrv", label: "Heart rate", icon: "♥", hint: "Heart rate in every session, and resting heart-rate variability (HRV)" },
  { slug: "imu", label: "Wrist sensors", icon: "▤", hint: "Punch force and rotation from the sensors on each wrist" },
  { slug: "observations", label: "Observations", icon: "✎", hint: "Progress over time, coach notes and AI training observations" },
  { slug: "medical", label: "Health notes", icon: "▣", hint: "Allergies, medications, conditions and pupil readings" },
  { slug: "team", label: "Team", icon: "◈", hint: "This fighter's coaches, physicians and gym" },
];

/** The fighter tabs this account may open (the API checks each). */
export function fighterTabsFor(user: AuthUser | null | undefined) {
  if (!user) return [];
  if (user.is_researcher) return FIGHTER_TABS;
  switch (user.role) {
    case "admin":
      return FIGHTER_TABS.filter((t) => ["", "team"].includes(t.slug));
    case "gym_manager":
      return FIGHTER_TABS.filter((t) => t.slug !== "medical");
    case "physician":
      return FIGHTER_TABS.filter((t) => ["", "sessions", "hrv", "medical", "team"].includes(t.slug));
    default:
      return FIGHTER_TABS;
  }
}

/** Who may start a training session from a fighter's page: their coaches, and researchers. */
export function canStartSession(user: AuthUser | null | undefined): boolean {
  return !!user && (user.role === "coach" || user.is_researcher);
}
