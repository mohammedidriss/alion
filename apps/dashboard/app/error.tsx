"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="text-4xl">Something went wrong</div>
      <p className="max-w-md text-sm text-neutral-400">
        {error.message || "An unexpected error occurred. Please try again."}
      </p>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-medium text-black hover:bg-emerald-400"
        >
          Try again
        </button>
        <a
          href="/"
          className="rounded-xl border border-white/10 px-5 py-2.5 text-sm text-neutral-300 hover:bg-white/[0.04]"
        >
          Go to home
        </a>
      </div>
    </div>
  );
}
