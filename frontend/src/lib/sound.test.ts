import { beforeAll, describe, expect, it, vi } from "vitest";
import { play, setSoundEnabled, setSoundVolume, SOUNDS, type SoundName } from "./sound";

/** A recording AudioContext: counts the voices each sound starts and the loudest gain it asks for. */
function fakeContext() {
  const started: number[] = [];
  const gains: number[] = [];
  const node = () => ({ connect: () => node() });
  const param = () => ({ value: 0, setValueAtTime: () => undefined, linearRampToValueAtTime: (v: number) => { gains.push(v); }, exponentialRampToValueAtTime: () => undefined });
  return {
    started, gains, currentTime: 0, state: "running", sampleRate: 48000, destination: {},
    resume: () => Promise.resolve(),
    createGain: () => ({ gain: param(), connect: () => node() }),
    createBiquadFilter: () => ({ type: "", frequency: { value: 0 }, Q: { value: 0 }, connect: () => node() }),
    createOscillator: () => ({ type: "", frequency: param(), connect: () => node(), start: (t: number) => { started.push(t); }, stop: () => undefined }),
    createBuffer: (_c: number, n: number) => ({ getChannelData: () => new Float32Array(n) }),
    createBufferSource: () => ({ buffer: null, connect: () => node(), start: (t: number) => { started.push(t); } }),
  };
}

// sound.ts keeps the first AudioContext it makes, so one fake serves the whole file.
const ctx = fakeContext();
const reset = () => { ctx.started.length = 0; ctx.gains.length = 0; };
let built = 0;

describe("sound palette", () => {
  beforeAll(() => {
    vi.stubGlobal("AudioContext", function () { built += 1; return ctx; });
    setSoundVolume(1);
  });

  it("builds the context once, after the gesture's frame, and then plays the sound that waited", async () => {
    play("move");
    window.dispatchEvent(new Event("pointerdown"));
    expect(built).toBe(0);
    await new Promise((r) => requestAnimationFrame(() => setTimeout(r)));
    expect(built).toBe(1);
    expect(ctx.started.length).toBeGreaterThan(0);
    play("move");
    expect(built).toBe(1);
  });

  it("names the moment every sound answers", () => {
    for (const when of Object.values(SOUNDS)) expect(when.length).toBeGreaterThan(3);
  });

  it("every sound starts at least one voice and stays under the master ceiling", () => {
    setSoundEnabled(true);
    for (const name of Object.keys(SOUNDS) as SoundName[]) {
      reset();
      play(name);
      expect(ctx.started.length, name).toBeGreaterThan(0);
      expect(Math.max(...ctx.gains), name).toBeLessThanOrEqual(0.7); // the capture tock is the loudest voice, 0.66 before the 0.35 master
    }
  });

  it("mute stops every sound", () => {
    setSoundEnabled(false);
    reset();
    play("move");
    expect(ctx.started.length).toBe(0);
  });
});
