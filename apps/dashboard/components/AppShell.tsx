"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading } = useAuth();

  // Login page — never show sidebar
  if (pathname === "/") {
    return <>{children}</>;
  }

  // Still loading auth state — show skeleton with sidebar space to avoid layout flash
  if (loading) {
    return (
      <div className="flex h-screen overflow-hidden">
        <div className="w-56 shrink-0 border-r border-white/5 bg-[#0d0d12]" />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    );
  }

  // Not authenticated — no sidebar
  if (!user) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
