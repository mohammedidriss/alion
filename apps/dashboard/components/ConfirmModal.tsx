"use client";

/** A destructive action's confirmation, optionally asking to type a name first. */

import { useState } from "react";

export function ConfirmModal({
  title,
  body,
  requireTyped,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: string;
  requireTyped?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const enabled = !requireTyped || typed === requireTyped;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-2xl border border-white/5 bg-[#13131a] p-5 shadow-xl">
        <h3 className="font-medium">{title}</h3>
        <p className="mt-2 text-sm text-neutral-400">{body}</p>
        {requireTyped && (
          <div className="mt-3">
            <label className="text-xs text-neutral-400">
              Type <span className="font-mono text-red-300">{requireTyped}</span> to
              confirm
            </label>
            <input
              autoFocus
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && enabled) onConfirm();
              }}
              className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-red-500/50 focus:outline-none"
              placeholder={requireTyped}
            />
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-xl bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!enabled}
            className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-red-900/40 disabled:text-red-300/50"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
