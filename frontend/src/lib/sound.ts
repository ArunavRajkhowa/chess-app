/* Synthesised board sounds (no audio assets, no licences). The context is created on the first
   user gesture because browsers refuse autoplay. Pieces are a soft wooden "tock"; notices are
   mallet tones (marimba-like: fundamental plus a quiet fourth partial). No square or saw waves. */

export type SoundName =
  | "move" | "capture" | "check" | "castle" | "promote" | "illegal"
  | "win" | "lose" | "draw" | "notify" | "lowTime" | "correct" | "wrong";

const MASTER_GAIN = 0.35; // the loudest sound at volume 1 stays well below a notification ping
const MASTER_LOWPASS_HZ = 5200; // takes the edge off every transient

let ctx: AudioContext | null = null;
let out: AudioNode | null = null;
let enabled = true;
let volume = 0.8;

export function setSoundEnabled(on: boolean): void { enabled = on; }
export function setSoundVolume(v: number): void { volume = Math.max(0, Math.min(1, v)); }

function context(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  if (!ctx) {
    ctx = new AudioContext();
    const master = ctx.createGain();
    master.gain.value = MASTER_GAIN;
    const soften = ctx.createBiquadFilter();
    soften.type = "lowpass";
    soften.frequency.value = MASTER_LOWPASS_HZ;
    master.connect(soften).connect(ctx.destination);
    out = master;
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

const jitter = () => 1 + (Math.random() - 0.5) * 0.06;

/** A sine voice with a soft attack and an exponential tail; `drop` glides the pitch down. */
function voice(c: AudioContext, freq: number, start: number, dur: number, gain: number, drop = 1, attack = 0.004) {
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = "sine";
  o.frequency.setValueAtTime(freq, start);
  if (drop !== 1) o.frequency.exponentialRampToValueAtTime(freq * drop, start + dur);
  g.gain.setValueAtTime(0, start);
  g.gain.linearRampToValueAtTime(gain * volume, start + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
  o.connect(g).connect(out!);
  o.start(start);
  o.stop(start + dur + 0.02);
}

/** The felt-on-wood touch: a very short band-passed noise burst. */
function touch(c: AudioContext, start: number, centre: number, gain: number) {
  const dur = 0.03;
  const n = Math.floor(c.sampleRate * dur);
  const buf = c.createBuffer(1, n, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 4);
  const src = c.createBufferSource();
  src.buffer = buf;
  const f = c.createBiquadFilter();
  f.type = "bandpass";
  f.frequency.value = centre;
  f.Q.value = 1.4;
  const g = c.createGain();
  g.gain.value = gain * volume;
  src.connect(f).connect(g).connect(out!);
  src.start(start);
}

function tock(c: AudioContext, start: number, pitch: number, weight: number) {
  const j = jitter();
  touch(c, start, 1300 * j, 0.5 * weight);
  voice(c, pitch * j, start, 0.09, 0.55 * weight, 0.6);
}

function mallet(c: AudioContext, freq: number, start: number, dur: number, gain: number) {
  voice(c, freq, start, dur, gain, 1, 0.008);
  voice(c, freq * 4, start, dur * 0.25, gain * 0.12, 1, 0.003);
}

export function play(name: SoundName): void {
  if (!enabled) return;
  const c = context();
  if (!c) return;
  const t = c.currentTime + 0.005;
  switch (name) {
    case "move": tock(c, t, 340, 1); break;
    case "capture": tock(c, t, 250, 1.2); touch(c, t + 0.035, 900, 0.25); break;
    case "castle": tock(c, t, 340, 0.9); tock(c, t + 0.085, 300, 0.8); break;
    case "check": tock(c, t, 340, 1); mallet(c, 880, t + 0.03, 0.35, 0.22); break;
    case "promote": tock(c, t, 340, 0.9); mallet(c, 659, t + 0.05, 0.3, 0.22); mallet(c, 988, t + 0.15, 0.45, 0.2); break;
    case "illegal": voice(c, 170, t, 0.14, 0.35, 0.8); break;
    case "win": [523, 659, 784, 1047].forEach((f, i) => mallet(c, f, t + i * 0.11, 0.7, 0.24)); break;
    case "lose": mallet(c, 440, t, 0.5, 0.22); mallet(c, 349, t + 0.18, 0.8, 0.2); break;
    case "draw": mallet(c, 523, t, 0.45, 0.2); mallet(c, 523, t + 0.2, 0.6, 0.18); break;
    case "notify": mallet(c, 784, t, 0.4, 0.2); break;
    case "lowTime": touch(c, t, 2000, 0.35); touch(c, t + 0.16, 2000, 0.3); break;
    case "correct": mallet(c, 784, t, 0.3, 0.22); mallet(c, 1175, t + 0.09, 0.45, 0.2); break;
    case "wrong": mallet(c, 330, t, 0.3, 0.2); mallet(c, 294, t + 0.12, 0.45, 0.18); break;
  }
}
