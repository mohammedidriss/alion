"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Home", icon: "▢" },
  { href: "/fighters", label: "Fighters", icon: "👤" },
  { href: "/sessions", label: "Sessions", icon: "▷" },
  { href: "/reports", label: "Reports", icon: "▤" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-16 flex-col items-center gap-2 border-r border-white/5 bg-[#0d0d12] py-4">
        <Link
          href="/"
          className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-emerald-400 text-sm font-bold text-black"
          aria-label="Alion home"
        >
          A
        </Link>
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            title={n.label}
            className={`nav-icon ${isActive(n.href) ? "nav-icon-active" : ""}`}
          >
            <span aria-hidden>{n.icon}</span>
            <span className="sr-only">{n.label}</span>
          </Link>
        ))}
      </aside>
      <main className="flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
