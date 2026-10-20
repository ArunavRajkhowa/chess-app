import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setSoundEnabled, setSoundVolume } from "../lib/sound";
import { setNarration } from "../lib/speech";

export const BOARD_THEMES = ["ink", "boxwood", "walnut", "slate"] as const;
export type BoardTheme = (typeof BOARD_THEMES)[number];

interface SettingsState {
  boardTheme: BoardTheme;
  pieceSet: "cburnett";
  sound: boolean;
  volume: number;
  showCoordinates: boolean;
  showLegalMoves: boolean;
  animation: boolean;
  autoQueen: boolean;
  confirmResign: boolean;
  playerName: string;
  /** Lessons and master games read aloud through the browser's own voices. */
  narration: boolean;
  narrationRate: number;
  narrationVoice: string; // a voice name, or "" for the best English voice the browser has
  set: (patch: Partial<Omit<SettingsState, "set">>) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      boardTheme: "ink",
      pieceSet: "cburnett",
      sound: true,
      volume: 0.8,
      showCoordinates: true,
      showLegalMoves: true,
      animation: true,
      autoQueen: false,
      confirmResign: true,
      playerName: "You",
      narration: true,
      narrationRate: 1,
      narrationVoice: "",
      set: (patch) => {
        if (patch.sound !== undefined) setSoundEnabled(patch.sound);
        if (patch.volume !== undefined) setSoundVolume(patch.volume);
        set(patch);
        const s = useSettings.getState();
        setNarration(s.narration, s.narrationRate, s.narrationVoice);
      },
    }),
    {
      name: "chess-coach-settings",
      version: 1,
      // Version 0 had chess.com-style themes (green, brown, blue, purple): unknown names fall back to ink.
      migrate: (state) => {
        const s = state as SettingsState;
        return { ...s, boardTheme: BOARD_THEMES.includes(s.boardTheme) ? s.boardTheme : "ink" };
      },
      onRehydrateStorage: () => (state) => {
        if (state) {
          setSoundEnabled(state.sound);
          setSoundVolume(state.volume);
          setNarration(state.narration ?? true, state.narrationRate ?? 1, state.narrationVoice ?? "");
        }
      },
    },
  ),
);
