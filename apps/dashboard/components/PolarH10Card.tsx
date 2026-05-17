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
 * Compact inline card for the fighter dashboard header.
 * Scans / pairs a Polar H10 and persists the address in localStorage
 * so the session page can auto-start BLE streaming with capture.
 */
export function PolarH10Card() {
  const [paired, setPaired] = useState<BleDevice | null>(null);
  const [devices, setDevices] = useState<BleDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setPaired(getPairedDevice());
  }, []);

  const scan = async () => {
    setScanning(true);
    setErr(null);
    try {
      const res = await api.scanBleDevices();
      setDevices(res.devices);
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
    <div className="flex items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-950/60 px-3 py-1.5">
      {/* Icon + label */}
      <span className="text-xs font-medium text-neutral-300">Polar H10</span>
      <span className="rounded-full bg-blue-900/50 px-1.5 py-0.5 text-[9px] font-medium text-blue-300">
        BLE
      </span>

      {err && <span className="text-[10px] text-red-400">error</span>}

      {paired ? (
        <>
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {paired.name.replace("Polar H10 ", "")}
          </span>
          <button
            onClick={unpair}
            className="text-[10px] text-neutral-600 hover:text-red-400"
            title="Unpair device"
          >
            ×
          </button>
        </>
      ) : (
        <>
          <button
            onClick={scan}
            disabled={scanning}
            className="rounded bg-blue-600 px-2 py-0.5 text-[11px] font-medium hover:bg-blue-500 disabled:opacity-50"
          >
            {scanning ? "Scanning…" : "Scan"}
          </button>
          {devices.length > 1 &&
            devices.map((d) => (
              <button
                key={d.address}
                onClick={() => pair(d)}
                className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] hover:border-blue-500"
              >
                {d.name.replace("Polar H10 ", "")}
              </button>
            ))}
        </>
      )}
    </div>
  );
}
