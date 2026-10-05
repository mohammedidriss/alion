"use client";

/**
 * Camera station — a phone links to the coach's studio once (one QR, ever) and
 * then follows whatever the coach has open: each new training session or dataset
 * take is joined automatically, and Start / Stop work as usual. The link is kept
 * in this browser, and the screen is kept awake between captures.
 *
 * A phone never switches capture while it's counting down, recording or still
 * uploading the last clip — it finishes first.
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { CameraNode } from "@/components/CameraNode";
import { api, type StationState } from "@/lib/api";

const LINK_KEY = "alion.studio";
const PHONE_KEY = "alion.phoneId";
const NAME_KEY = "alion.phoneName"; // the camera's name — the phone's model unless renamed

type Active = NonNullable<StationState["active"]>;

function phoneLabel(): string {
  const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  const m = ua.match(/Android [\d.]+; ([^;)]+)/);
  return m ? m[1].trim().slice(0, 30) : "phone";
}

export default function CameraStationPage() {
  // useSearchParams needs a Suspense boundary on a statically rendered page.
  return (
    <Suspense fallback={null}>
      <CameraStation />
    </Suspense>
  );
}

function CameraStation() {
  const search = useSearchParams();
  const [link, setLink] = useState<string | null>(null);
  const [phoneId, setPhoneId] = useState("");
  const [name, setName] = useState("phone");
  const [active, setActive] = useState<Active | null>(null);
  const [linkErr, setLinkErr] = useState<string | null>(null);
  const [online, setOnline] = useState(true);
  const busyRef = useRef(false);
  const pendingRef = useRef<Active | null>(null);

  // The studio link: from the QR the first time, then remembered on this phone.
  useEffect(() => {
    const fromQr = search.get("studio");
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(LINK_KEY);
      if (fromQr) localStorage.setItem(LINK_KEY, fromQr);
      let pid = localStorage.getItem(PHONE_KEY);
      if (!pid) {
        pid = Math.random().toString(36).slice(2, 10);
        localStorage.setItem(PHONE_KEY, pid);
      }
      setPhoneId(pid);
      setName(localStorage.getItem(NAME_KEY) || phoneLabel());
    } catch {
      setName(phoneLabel());
      setPhoneId(Math.random().toString(36).slice(2, 10));
    }
    setLink(fromQr ?? stored);
  }, [search]);

  // Keep the screen on between captures (re-requested when the page is shown again).
  useEffect(() => {
    let lock: { release: () => Promise<void> } | null = null;
    const request = async () => {
      try {
        const wl = (navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } }).wakeLock;
        if (wl && document.visibilityState === "visible") lock = await wl.request("screen");
      } catch {
        /* not supported or refused — the phone may dim; recording still works */
      }
    };
    request();
    const onVis = () => document.visibilityState === "visible" && request();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      lock?.release().catch(() => {});
    };
  }, []);

  const adopt = useCallback((next: Active | null) => {
    setActive((cur) => {
      const same = cur && next && cur.kind === next.kind && cur.id === next.id;
      if (same || (!cur && !next)) return cur;
      if (busyRef.current) {
        pendingRef.current = next; // switch once this capture is done
        return cur;
      }
      return next;
    });
  }, []);

  // Follow the studio.
  useEffect(() => {
    if (!link || !phoneId) return;
    let alive = true;
    const poll = async () => {
      try {
        const st = await api.stationState(link, phoneId, name);
        if (!alive) return;
        setOnline(true);
        setLinkErr(null);
        adopt(st.active);
      } catch (e) {
        if (!alive) return;
        const msg = String(e);
        if (msg.startsWith("403")) setLinkErr("This link isn't valid any more — scan the coach's QR again.");
        else setOnline(false);
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [link, phoneId, name, adopt]);

  const rename = useCallback((next: string) => {
    setName(next);
    try {
      localStorage.setItem(NAME_KEY, next);
    } catch {
      /* not remembered — still used for this capture */
    }
  }, []);

  const onBusy = useCallback((busy: boolean) => {
    busyRef.current = busy;
    if (!busy && pendingRef.current !== null) {
      const next = pendingRef.current;
      pendingRef.current = null;
      setActive(next);
    }
  }, []);

  if (!link) {
    return (
      <Shell>
        <p className="text-sm text-neutral-300">
          Scan the QR on the coach&apos;s laptop to link this phone. You only need to do it once.
        </p>
      </Shell>
    );
  }
  if (linkErr) {
    return (
      <Shell>
        <p className="text-sm text-red-300">{linkErr}</p>
      </Shell>
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-3 p-4">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-emerald-300">
          <span className={`h-2 w-2 rounded-full ${online ? "bg-emerald-500" : "bg-amber-500"}`} />
          {online ? "Linked to the coach" : "Reconnecting…"}
        </span>
        <span className="text-neutral-500">
          {active ? (active.kind === "take" ? "Dataset take" : "Training session") : "Waiting"}
        </span>
      </div>
      {active ? (
        <CameraNode
          key={`${active.kind}:${active.id}`}
          sessionId={active.kind === "session" ? active.id : undefined}
          takeId={active.kind === "take" ? active.id : undefined}
          token={active.join_token}
          defaultLabel={name}
          onBusy={onBusy}
          onLabelChange={rename}
        />
      ) : (
        <Shell>
          <p className="text-sm text-neutral-300">
            Linked. This phone joins the next session or take the coach opens — leave this page
            open.
          </p>
        </Shell>
      )}
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-md p-6">
      <div className="rounded-2xl border border-white/10 bg-neutral-950 p-5">
        <div className="mb-2 text-base font-semibold">Alion camera</div>
        {children}
      </div>
    </div>
  );
}
