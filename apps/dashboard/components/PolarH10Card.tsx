"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

type BleDevice = { name: string; address: string };

const LS_KEY_ADDR = "polar_h10_address";
const LS_KEY_NAME = "polar_h10_name";

/** Read the paired Polar H10 from localStorage (shared across pages). */
export function getPairedDevice(): BleDevice | null {
  if (typeof window === "undefined") return null;
  const address = localStorage.getItem(LS_KEY_ADDR);
  const name = localStorage.getItem(LS_KEY_NAME);
  return address ? { address, name: name ?? "Polar H10" } : null;
}

/**
 * Card shown on the fighter dashboard for scanning and pairing a Polar H10.
 * The selected device address is persisted in localStorage so the session page
 * can auto-start BLE streaming when capture begins.
 */
export function PolarH10Card() {
  const [paired, setPaired] = useState<BleDevice | null>(null);
  const [devices, setDevices] = useState<BleDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Load persisted pairing on mount.
  useEffect(() => {
    setPaired(getPairedDevice());
  }, []);

  const scan = async () => {
    setScanning(true);
    setErr(null);
    try {
      const res = await api.scanBleDevices();
      setDevices(res.devices);
      // Auto-pair if exactly one device found.
      if (res.devices.length === 1) {
        pair(res.devices[0]);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setScanning(false);
    }
  };

  const pair = (d: BleDevice) => {
    localStorage.setItem(LS_KEY_ADDR, d.address);
    localStorage.setItem(LS_KEY_NAME, d.name);
    setPaired(d);
  };

  const unpair = () => {
    localStorage.removeItem(LS_KEY_ADDR);
    localStorage.removeItem(LS_KEY_NAME);
    setPaired(null);
    setDevices([]);
  };

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-center gap-2">
        <h2 className="font-medium">Polar H10</h2>
        <span className="rounded-full bg-blue-900/50 px-2 py-0.5 text-[10px] font-medium text-blue-300">
          BLE
        </span>
        {paired && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
            Paired
          </span>
        )}
      </div>

      <p className="mt-1 text-xs text-neutral-500">
        Pair a Polar H10 chest strap here. It will automatically start streaming
        live HR + RR intervals when you begin a session.
      </p>

      {err && <p className="mt-2 text-xs text-red-400">{err}</p>}

      {paired ? (
        <div className="mt-3 flex items-center gap-3">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-sm">
            <span className="font-medium text-emerald-300">{paired.name}</span>
            <span className="ml-2 text-xs text-neutral-500">
              {paired.address.slice(-8)}
            </span>
          </div>
          <button
            onClick={unpair}
            className="text-xs text-neutral-500 hover:text-red-400"
          >
            Unpair
          </button>
          <button
            onClick={scan}
            disabled={scanning}
            className="text-xs text-neutral-500 hover:text-neutral-300"
          >
            {scanning ? "Scanning..." : "Re-scan"}
          </button>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <button
            onClick={scan}
            disabled={scanning}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
          >
            {scanning ? "Scanning..." : "Scan for devices"}
          </button>

          {devices.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {devices.map((d) => (
                <button
                  key={d.address}
                  onClick={() => pair(d)}
                  className="rounded border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm hover:border-blue-500 hover:bg-blue-500/10"
                >
                  {d.name}{" "}
                  <span className="text-xs text-neutral-500">
                    ({d.address.slice(-8)})
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
