"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { MobileTopBar, MobileBottomBar } from "@/components/MobileNav";
import { useAuth } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => { setSidebarOpen(false); }, [pathname]);

  useEffect(() => {
    if (!loading && !user && pathname !== "/") {
      router.push("/");
    }
  }, [loading, user, pathname, router]);

  if (pathname === "/") return <>{children}</>;

  if (loading) {
    return (
      <div className="flex h-screen overflow-hidden">
        <div className="hidden md:block w-56 shrink-0 border-r border-white/5 bg-[#0d0d12]" />
        <main className="mobile-shell-main flex-1 overflow-y-auto">{children}</main>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center text-neutral-400">
        Redirecting to sign in…
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#0a0a0f]">
      {/* Mobile top bar — hidden on desktop */}
      <MobileTopBar onMenuToggle={() => setSidebarOpen((o) => !o)} menuOpen={sidebarOpen} />

      {/* Sidebar overlay backdrop — mobile only */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/70 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — slide-in on mobile, always visible on desktop */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 w-72 transform transition-transform duration-200 ease-in-out
          md:relative md:w-56 md:translate-x-0
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <main className="mobile-shell-main flex-1 overflow-y-auto">
        {children}
      </main>

      {/* Mobile bottom tab bar — hidden on desktop */}
      <MobileBottomBar />
    </div>
  );
}
