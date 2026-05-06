import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Alion",
  description: "Multi-modal AI coaching dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-neutral-100 antialiased">{children}</body>
    </html>
  );
}
