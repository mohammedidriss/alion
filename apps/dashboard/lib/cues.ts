/**
 * Audio cues for hands-free recording: beeps scheduled on the audio clock (exact
 * spacing, unaffected by a busy page) and spoken prompts. Browsers only allow
 * sound after a user gesture, so `unlockCues()` must run inside a click handler.
 */

type Ctx = AudioContext;
let ctx: Ctx | null = null;
const pending = new Set<OscillatorNode>(); // scheduled beeps not yet played

function audio(): Ctx | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const C =
      (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!C) return null;
    ctx = new C();
  }
  return ctx;
}

/** Call from a click/tap: lets later beeps and speech play without a gesture. */
export function unlockCues(): void {
  const c = audio();
  if (c && c.state === "suspended") void c.resume();
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    // Safari unlocks speech on the first utterance spoken inside a gesture.
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(""));
  }
}

/** Audio-clock seconds now (beeps are scheduled relative to this). */
export function cueNow(): number {
  return audio()?.currentTime ?? 0;
}

/** A short beep `at` audio-clock seconds (default: now). */
export function beep(
  { at, freq = 880, ms = 90, gain = 0.25 }: { at?: number; freq?: number; ms?: number; gain?: number } = {},
): void {
  const c = audio();
  if (!c) return;
  const t = at ?? c.currentTime;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.005);
  g.gain.setValueAtTime(gain, t + ms / 1000 - 0.01);
  g.gain.linearRampToValueAtTime(0, t + ms / 1000);
  osc.connect(g).connect(c.destination);
  pending.add(osc);
  osc.onended = () => pending.delete(osc);
  osc.start(t);
  osc.stop(t + ms / 1000 + 0.02);
}

/** Speak a prompt (cancels anything still being said). */
export function say(text: string): void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  window.speechSynthesis.speak(u);
}

/** Silence everything: speech and every beep scheduled but not yet played. */
export function hushCues(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  for (const osc of pending) {
    try {
      osc.stop();
      osc.disconnect();
    } catch {
      /* already stopped */
    }
  }
  pending.clear();
}
