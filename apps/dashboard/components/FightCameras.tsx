"use client";

/**
 * A fight's phone cameras (ADR-063): the studio QR — scanned once per phone, ever —
 * and each linked phone's corner, picked once and remembered for every fight after.
 * Opening the fight points the studio at it, so every linked phone joins its
 * corner's recording on its own; Start fight starts them all together.
 */

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { QR_PX, phoneUrl } from "@/components/JoinQrCard";
import { api, type FightCorner, type Studio } from "@/lib/api";

const CORNERS: [FightCorner | null, string][] = [
  ["red", "Red"],
  ["blue", "Blue"],
  [null, "Off"],
];

export function FightCameras({ boutId, red, blue }: { boutId: string; red: number; blue: number }) {
  const [studio, setStudio] = useState<Studio | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .setStudioActive("bout", boutId)
      .then((st) => alive && setStudio(st))
      .catch(() => alive && setErr("Couldn't point the linked phones at this fight."));
    const poll = setInterval(() => {
      api
        .studio()
        .then((st) => alive && setStudio(st))
        .catch(() => {});
    }, 3000);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, [boutId]);

  const pick = (phoneId: string, corner: FightCorner | null) => {
    api
      .setStudioPhoneCorner(phoneId, corner)
      .then(setStudio)
      .catch(() => setErr("Couldn't save that phone's corner."));
  };

  const phones = studio?.phones ?? [];
  const unassigned = phones.filter((p) => !p.corner).length;
  return (
    <section className="flex flex-wrap items-start gap-4 rounded-2xl border border-white/10 p-3">
      {studio ? (
        <div className="shrink-0 overflow-hidden rounded-lg bg-white">
          <QRCodeSVG value={phoneUrl(studio.join_path, studio.lan_ip)} size={QR_PX} marginSize={4} />
        </div>
      ) : (
        <div
          className="flex shrink-0 items-center justify-center rounded-lg border border-dashed border-white/10 text-xs text-neutral-500"
          style={{ width: QR_PX, height: QR_PX }}
        >
          {err ? "No link" : "…"}
        </div>
      )}
      <div className="min-w-[14rem] flex-1 space-y-2">
        <div>
          <div className="text-sm font-semibold text-neutral-200">Phone cameras</div>
          <p className="text-xs text-neutral-500">
            A phone scans this once, ever. Pick its corner once — it&apos;s remembered for every fight. Linked
            phones join their corner on their own; Start fight starts them all.
          </p>
        </div>
        <div className="text-xs">
          <span className={red > 0 ? "text-red-300" : "text-neutral-500"}>Red: {red} ready</span>
          <span className="mx-2 text-neutral-600">·</span>
          <span className={blue > 0 ? "text-sky-300" : "text-neutral-500"}>Blue: {blue} ready</span>
          {unassigned > 0 && (
            <span className="ml-2 text-amber-300">
              · {unassigned} phone{unassigned === 1 ? "" : "s"} without a corner
            </span>
          )}
        </div>
        {phones.length === 0 ? (
          <p className="text-xs text-neutral-600">
            No phone linked and open. Open the RingsideIQ camera page on each phone, or scan the QR.
          </p>
        ) : (
          <ul className="space-y-1">
            {phones.map((p) => (
              <li key={p.phone_id} className="flex items-center gap-2 text-xs">
                <span className="w-32 truncate text-neutral-200">{p.label}</span>
                {CORNERS.map(([c, label]) => {
                  const on = (p.corner ?? null) === c;
                  return (
                    <button
                      key={label}
                      onClick={() => pick(p.phone_id, c)}
                      className={`rounded-lg px-2 py-0.5 ${
                        on
                          ? c === "red"
                            ? "bg-red-600 text-white"
                            : c === "blue"
                              ? "bg-sky-600 text-white"
                              : "bg-white/15 text-neutral-200"
                          : "border border-white/10 text-neutral-400 hover:bg-white/5"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </li>
            ))}
          </ul>
        )}
        {err && <p className="text-xs text-red-300">{err}</p>}
      </div>
    </section>
  );
}
