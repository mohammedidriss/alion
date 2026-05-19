"use client";

import { useEffect } from "react";

/**
 * Initialises the Capgo OTA updater when the app is running inside a native
 * Capacitor shell (iOS / Android).  Has no effect in the browser.
 *
 * With the `server.url` architecture, the app always loads from the live
 * deployment so OTA is only needed for native-layer patches.
 */
export function CapgoUpdater() {
  useEffect(() => {
    import("@capgo/capacitor-updater").then(({ CapacitorUpdater }) => {
      CapacitorUpdater.notifyAppReady();
    }).catch(() => {
      // Not running in Capacitor — ignore.
    });
  }, []);

  return null;
}
