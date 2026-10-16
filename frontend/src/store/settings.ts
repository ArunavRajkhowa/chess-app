import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setSoundEnabled, setSoundVolume } from "../lib/sound";

export type BoardTheme = "green" | "brown" | "blue" | "purple" | "walnut";

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
  set: (patch: Partial<Omit<SettingsState, "set">>) => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      boardTheme: "green",
      pieceSet: "cburnett",
      sound: true,
      volume: 0.8,
      showCoordinates: true,
      showLegalMoves: true,
      animation: true,
      autoQueen: false,
      confirmResign: true,
      playerName: "You",
      set: (patch) => {
        if (patch.sound !== undefined) setSoundEnabled(patch.sound);
        if (patch.volume !== undefined) setSoundVolume(patch.volume);
        set(patch);
      },
    }),
    {
      name: "chess-coach-settings",
      onRehydrateStorage: () => (state) => {
        if (state) {
          setSoundEnabled(state.sound);
          setSoundVolume(state.volume);
        }
      },
    },
  ),
);
