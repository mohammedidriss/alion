import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor config — mobile shell for the Alion dashboard.
 *
 * Architecture: the mobile app is a WebView that loads the deployed Next.js
 * app directly from the server.  This avoids static-export limitations and
 * means every web deployment is immediately reflected in the mobile app
 * without an app-store submission.
 *
 * Update flow:
 *  - Web changes  → deploy to Vercel/server → mobile picks up on next open (no action needed)
 *  - Native changes (new plugins, permissions) → rebuild & submit to app stores
 *
 * To test locally, set CAPACITOR_SERVER_URL=http://<your-machine-ip>:3000
 * so the device (or simulator) can reach your dev server.
 */

const DEV_SERVER = process.env.CAPACITOR_SERVER_URL;

const config: CapacitorConfig = {
  appId: 'ai.alion.app',
  appName: 'Alion',

  // webDir is still needed for the initial bundle (shown while the live URL
  // loads, and as a fallback when offline).
  webDir: 'out',

  server: DEV_SERVER
    ? {
        // Dev mode: point at local Next.js dev server
        url: DEV_SERVER,
        cleartext: true,
      }
    : {
        // Production: set CAPACITOR_PROD_URL to your deployed frontend URL.
        // Works with any host — Vercel, AWS CloudFront, Azure Static Web Apps,
        // GCP Cloud Run, Nginx on a VPS, etc.
        // Example: https://app.yourdomain.com
        url: process.env.CAPACITOR_PROD_URL ?? 'https://alion-dashboard.vercel.app',
        cleartext: false,
      },

  plugins: {
    CapacitorUpdater: {
      // OTA updates are less relevant when using server.url (the server
      // always serves the latest code), but keep it for native-layer updates.
      autoUpdate: false,
    },
  },

  ios: {
    backgroundColor: '#000000',
  },

  android: {
    backgroundColor: '#000000',
  },
};

export default config;
