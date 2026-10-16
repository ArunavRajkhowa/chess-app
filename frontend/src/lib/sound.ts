/* Synthesised board sounds (no audio assets, no licences). The context is created on the first
   user gesture because browsers refuse autoplay. */

export type SoundName =
  | "move" | "capture" | "check" | "castle" | "promote" | "illegal"
  | "win" | "lose" | "draw" | "notify" | "lowTime" | "correct" | "wrong";

let ctx: AudioContext | null = null;
let enabled = true;
let volume = 0.8;

export function setSoundEnabled(on: boolean): void { enabled = on; }
export function setSoundVolume(v: number): void { volume = Math.max(0, Math.min(1, v)); }

function context(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function tone(c: AudioContext, freq: number, start: number, dur: number, type: OscillatorType, gain: number) {
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, start);
  g.gain.setValueAtTime(0, start);
  g.gain.linearRampToValueAtTime(gain * volume, start + 0.004);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  o.connect(g).connect(c.destination);
  o.start(start);
  o.stop(start + dur + 0.02);
}

function knock(c: AudioContext, start: number, dur: number, cutoff: number, gain: number) {
  const n = Math.floor(c.sampleRate * dur);
  const buf = c.createBuffer(1, n, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3);
  const src = c.createBufferSource();
  src.buffer = buf;
  const f = c.createBiquadFilter();
  f.type = "lowpass";
  f.frequency.value = cutoff;
  const g = c.createGain();
  g.gain.value = gain * volume;
  src.connect(f).connect(g).connect(c.destination);
  src.start(start);
}

export function play(name: SoundName): void {
  if (!enabled) return;
  const c = context();
  if (!c) return;
  const t = c.currentTime;
  switch (name) {
    case "move": knock(c, t, 0.07, 1800, 0.9); tone(c, 180, t, 0.05, "sine", 0.25); break;
    case "capture": knock(c, t, 0.12, 900, 1.1); tone(c, 110, t, 0.09, "triangle", 0.35); break;
    case "castle": knock(c, t, 0.06, 1800, 0.8); knock(c, t + 0.09, 0.06, 1500, 0.7); break;
    case "check": knock(c, t, 0.07, 1800, 0.8); tone(c, 880, t, 0.12, "sine", 0.18); tone(c, 1320, t + 0.02, 0.1, "sine", 0.1); break;
    case "promote": [523, 659, 784, 1047].forEach((f, i) => tone(c, f, t + i * 0.06, 0.18, "sine", 0.2)); break;
    case "illegal": tone(c, 160, t, 0.12, "square", 0.08); tone(c, 120, t + 0.1, 0.12, "square", 0.08); break;
    case "win": [523, 659, 784, 1047, 1319].forEach((f, i) => tone(c, f, t + i * 0.09, 0.35, "triangle", 0.22)); break;
    case "lose": [392, 349, 311, 262].forEach((f, i) => tone(c, f, t + i * 0.14, 0.35, "triangle", 0.2)); break;
    case "draw": [440, 440, 440].forEach((f, i) => tone(c, f, t + i * 0.16, 0.2, "sine", 0.18)); break;
    case "notify": tone(c, 987, t, 0.1, "sine", 0.15); tone(c, 1318, t + 0.1, 0.16, "sine", 0.15); break;
    case "lowTime": tone(c, 1200, t, 0.06, "square", 0.06); tone(c, 1200, t + 0.12, 0.06, "square", 0.06); break;
    case "correct": tone(c, 784, t, 0.1, "sine", 0.18); tone(c, 1175, t + 0.08, 0.2, "sine", 0.18); break;
    case "wrong": tone(c, 220, t, 0.18, "sawtooth", 0.06); break;
  }
}
