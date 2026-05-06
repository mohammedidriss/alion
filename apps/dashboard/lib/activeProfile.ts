"use client";

import { useEffect, useState } from "react";

export type ProfileKind = "fighter" | "coach" | "referee";

export interface ActiveProfile {
  kind: ProfileKind;
  id: string;
  name: string;
  photo_path: string | null;
}

const KEY = "alion.activeProfile";

/**
 * Lightweight profile selector — stored in localStorage. There's no real
 * authentication; this is a "who am I acting as" indicator that persists
 * across page reloads. Real auth would be a Phase 4 concern (multi-user
 * deployment); for a single-user dissertation tool a profile picker is
 * sufficient and avoids storing passwords.
 */
export function useActiveProfile(): {
  active: ActiveProfile | null;
  setActive: (p: ActiveProfile | null) => void;
} {
  const [active, setActiveState] = useState<ActiveProfile | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setActiveState(JSON.parse(raw));
    } catch {
      // localStorage may be unavailable (SSR / disabled) — silently no-op.
    }
  }, []);

  // Sync across tabs.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== KEY) return;
      try {
        setActiveState(e.newValue ? JSON.parse(e.newValue) : null);
      } catch {
        setActiveState(null);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setActive = (p: ActiveProfile | null) => {
    setActiveState(p);
    try {
      if (p) localStorage.setItem(KEY, JSON.stringify(p));
      else localStorage.removeItem(KEY);
    } catch {
      // ignore
    }
  };

  return { active, setActive };
}
