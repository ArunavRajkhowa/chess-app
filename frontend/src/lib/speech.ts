/* Narration. A sentence is first asked from the server (a neural voice, cached as MP3); when the
   server has no audio for it, the browser's own speech synthesis speaks it, sentence by sentence
   because Chrome cuts one long utterance off after about fifteen seconds. Nothing here throws: a
   browser without voices resolves at once, so a lecture keeps moving on its own reading timer. */

let enabled = true;
let rate = 1;
let voiceName = "";
let serial = 0; // the id of the latest speak(); an older one stops queueing sentences
let current: HTMLAudioElement | null = null;
const audio = new Map<string, Promise<string | null>>(); // text → object URL, or null when the server has none

export function setNarration(on: boolean, speed: number, voice: string): void {
  enabled = on;
  rate = Math.max(0.5, Math.min(2, speed));
  voiceName = voice;
  if (!on) stopSpeech();
}

export function speechAvailable(): boolean {
  return typeof window !== "undefined" && ("speechSynthesis" in window || "Audio" in window);
}

const synth = () => (typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null);

export function listVoices(): SpeechSynthesisVoice[] {
  return (synth()?.getVoices() ?? []).filter((v) => v.lang.toLowerCase().startsWith("en"));
}

/** The chosen voice, else the best English voice the browser has: natural ones first, then the local default. */
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = listVoices();
  if (!voices.length) return null;
  const named = voices.find((v) => v.name === voiceName);
  if (named) return named;
  const score = (v: SpeechSynthesisVoice) =>
    (/natural|neural|premium|enhanced/i.test(v.name) ? 4 : 0) + (/google/i.test(v.name) ? 2 : 0) + (v.default ? 1 : 0) + (v.lang.toLowerCase() === (navigator.language || "en").toLowerCase() ? 1 : 0);
  return voices.slice().sort((a, b) => score(b) - score(a))[0];
}

/** About 150 words a minute, the pace of a calm explanation; the floor keeps a short caption readable. */
export function readingTimeMs(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1500, (words / 2.5) * 1000) / rate;
}

function sentences(text: string): string[] {
  return text.replace(/\s+/g, " ").match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
}

function fetchAudio(text: string): Promise<string | null> {
  const key = text.trim();
  let p = audio.get(key);
  if (!p) {
    p = fetch(`/api/narration?text=${encodeURIComponent(key)}`)
      .then(async (r) => (r.status === 200 ? URL.createObjectURL(await r.blob()) : null))
      .catch(() => null);
    audio.set(key, p);
  }
  return p;
}

/** Asks the server for a sentence's audio ahead of time, so the next frame starts without a gap. */
export function prefetch(text: string): void {
  if (enabled && text.trim() && typeof fetch !== "undefined") void fetchAudio(text);
}

function playUrl(url: string, id: number): Promise<boolean> {
  return new Promise((resolve) => {
    const el = new Audio(url);
    el.playbackRate = rate;
    current = el;
    el.onended = () => { if (current === el) current = null; resolve(true); };
    el.onerror = () => { if (current === el) current = null; resolve(false); };
    el.play().catch(() => resolve(false)); // autoplay refused before any gesture: the caller falls back to its timer
    if (id !== serial) resolve(true);
  });
}

function speakBrowser(text: string, id: number): Promise<boolean> {
  const s = synth();
  const voice = pickVoice();
  if (!s || !voice) return Promise.resolve(false);
  s.cancel();
  return new Promise((resolve) => {
    const parts = sentences(text);
    let i = 0;
    const next = () => {
      if (id !== serial || i >= parts.length) return resolve(true);
      const u = new SpeechSynthesisUtterance(parts[i++]);
      u.voice = voice;
      u.lang = voice.lang;
      u.rate = rate;
      // Chrome sometimes drops the end event: a timer a little longer than the sentence steps on anyway.
      const guard = setTimeout(next, readingTimeMs(u.text) * 2 + 1500);
      u.onend = () => { clearTimeout(guard); next(); };
      u.onerror = (e) => { clearTimeout(guard); if (e.error === "interrupted" || e.error === "canceled") resolve(true); else next(); };
      s.speak(u);
    };
    next();
  });
}

/** Speaks the text; resolves true when it was spoken, false when nothing could speak it. */
export async function speak(text: string): Promise<boolean> {
  if (!enabled || !text.trim()) return false;
  const id = ++serial;
  stopCurrent();
  const url = await fetchAudio(text);
  if (id !== serial) return true;
  return url ? playUrl(url, id) : speakBrowser(text, id);
}

function stopCurrent(): void {
  if (current) { current.pause(); current = null; }
  synth()?.cancel();
}

export function stopSpeech(): void {
  serial++;
  stopCurrent();
}

const PIECE_WORDS: Record<string, string> = { K: "king", Q: "queen", R: "rook", B: "bishop", N: "knight" };

/** A move the way a coach says it: "Nxe5+" becomes "knight takes e5, check". */
export function spokenMove(san: string): string {
  const clean = san.replace(/[+#]$/, "");
  const suffix = san.endsWith("#") ? ", checkmate" : san.endsWith("+") ? ", check" : "";
  if (clean === "O-O") return `castles kingside${suffix}`;
  if (clean === "O-O-O") return `castles queenside${suffix}`;
  const m = /^([KQRBN])?([a-h])?([1-8])?(x)?([a-h][1-8])(?:=([QRBN]))?$/.exec(clean);
  if (!m) return san;
  const [, piece, fromFile, fromRank, takes, to, promo] = m;
  const words: string[] = [];
  if (piece) words.push(PIECE_WORDS[piece]);
  if (fromFile || fromRank) words.push(`${fromFile ?? ""}${fromRank ?? ""}`); // "Nbd2", "R1e2", "exd5"
  if (takes) words.push("takes");
  words.push(to);
  if (promo) words.push(`promotes to a ${PIECE_WORDS[promo]}`);
  return words.filter(Boolean).join(" ") + suffix;
}
