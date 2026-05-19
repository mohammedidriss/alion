"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Redirect unauthenticated users to login (must be in useEffect to avoid setState-during-render)
  useEffect(() => {
    if (!loading && !user && pathname !== "/") {
      router.push("/");
    }
  }, [loading, user, pathname, router]);

  // Login page — never show sidebar
  if (pathname === "/") {
    return <>{children}</>;
  }

  // Still loading auth state — show skeleton with sidebar space to avoid layout flash
  if (loading) {
    return (
      <div className="flex h-screen overflow-hidden">
        <div className="hidden md:block w-56 shrink-0 border-r border-white/5 bg-[#0d0d12]" />
        <main className="flex-1 overflow-y-auto pt-14 md:pt-0">{children}</main>
      </div>
    );
  }

  // Not authenticated — show redirect message (useEffect above handles the actual redirect)
  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center text-neutral-400">
        Redirecting to sign in...
      </div>
    );
  }

  const isDeepPage = pathname.split("/").filter(Boolean).length > 1;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile nav controls */}
      {isDeepPage ? (
        <>
          {/* Back arrow on deep pages */}
          <button
            onClick={() => router.back()}
            className="fixed left-3 top-3 z-50 rounded-lg bg-white/10 p-2 text-white md:hidden"
            aria-label="Go back"
          >
            ←
          </button>
          {/* Hamburger moves to right on deep pages */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="fixed right-3 top-3 z-50 rounded-lg bg-white/10 p-2 text-white md:hidden"
            aria-label="Toggle menu"
          >
            {sidebarOpen ? "✕" : "☰"}
          </button>
        </>
      ) : (
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="fixed left-3 top-3 z-50 rounded-lg bg-white/10 p-2 text-white md:hidden"
          aria-label="Toggle menu"
        >
          {sidebarOpen ? "✕" : "☰"}
        </button>
      )}

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — always visible on desktop, slide-in on mobile */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 w-56 transform transition-transform duration-200 ease-in-out
          md:relative md:translate-x-0
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>

      <main className="flex-1 overflow-y-auto pt-14 md:pt-0">{children}</main>
    </div>
  );
}
