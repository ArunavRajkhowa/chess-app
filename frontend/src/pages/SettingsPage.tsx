import { useEffect, useState } from "react";
import { useSettings, type BoardTheme } from "../store/settings";
import { AccountPanel } from "../components/account/AccountPanel";
import { Board } from "../components/board/Board";
import { play as playSound } from "../lib/sound";
import { listVoices, speak, speechAvailable } from "../lib/speech";

const THEMES: { key: BoardTheme; label: string }[] = [
  { key: "ink", label: "Ink" }, { key: "boxwood", label: "Boxwood" }, { key: "walnut", label: "Walnut" }, { key: "slate", label: "Slate" },
];

/** Lessons read aloud: on or off, how fast, and which of the browser's voices. */
function NarrationCard() {
  const s = useSettings();
  const [voices, setVoices] = useState(listVoices);
  useEffect(() => {
    if (!speechAvailable()) return;
    const refresh = () => setVoices(listVoices());
    window.speechSynthesis.addEventListener("voiceschanged", refresh);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", refresh);
  }, []);
  if (!speechAvailable()) return null;
  return (
    <div className="card stack" data-testid="narration">
      <div className="card-title"><h3>Narration</h3><span className="faint">lessons and games read aloud; the server's neural voice when it has one, else this browser's</span></div>
      <label className="row"><input type="checkbox" checked={s.narration} onChange={(e) => s.set({ narration: e.target.checked })} /> Narration on</label>
      <label className="row">Speed <input type="range" min={0.7} max={1.4} step={0.1} value={s.narrationRate} onChange={(e) => s.set({ narrationRate: Number(e.target.value) })} /> <span className="faint num">{s.narrationRate.toFixed(1)}×</span></label>
      <label className="row">Fallback voice
        <select className="select" value={s.narrationVoice} onChange={(e) => s.set({ narrationVoice: e.target.value })}>
          <option value="">Automatic</option>
          {voices.map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
        </select>
        <button className="btn btn-sm" onClick={() => void speak("Knight takes e5, check. The king must move, and the queen falls.")}>Test</button>
      </label>
    </div>
  );
}

export function SettingsPage() {
  const s = useSettings();
  return (
    <div className="stack" data-testid="settings">
      <div className="page-head"><div><h1>Settings</h1><p>Board, sound and play preferences. Saved in this browser.</p></div></div>
      <div className="settings-grid">
        <div className="stack">
          <AccountPanel />
          <div className="card">
            <div className="card-title"><h3>Board theme</h3></div>
            <div className="row" style={{ flexWrap: "wrap" }}>
              {THEMES.map((t) => (
                <button key={t.key} className={`btn btn-sm ${s.boardTheme === t.key ? "btn-primary" : ""}`} onClick={() => s.set({ boardTheme: t.key })} data-testid={`theme-${t.key}`}>{t.label}</button>
              ))}
            </div>
          </div>
          <div className="card stack">
            <div className="card-title"><h3>Play</h3></div>
            <label className="row"><input type="checkbox" checked={s.showLegalMoves} onChange={(e) => s.set({ showLegalMoves: e.target.checked })} /> Show legal moves</label>
            <label className="row"><input type="checkbox" checked={s.showCoordinates} onChange={(e) => s.set({ showCoordinates: e.target.checked })} /> Show coordinates</label>
            <label className="row"><input type="checkbox" checked={s.animation} onChange={(e) => s.set({ animation: e.target.checked })} /> Animate pieces</label>
            <label className="row"><input type="checkbox" checked={s.autoQueen} onChange={(e) => s.set({ autoQueen: e.target.checked })} /> Always promote to a queen</label>
            <label className="row"><input type="checkbox" checked={s.confirmResign} onChange={(e) => s.set({ confirmResign: e.target.checked })} /> Confirm before resigning</label>
            <label className="row">Your name <input className="input" style={{ width: 200 }} value={s.playerName} onChange={(e) => s.set({ playerName: e.target.value })} /></label>
          </div>
          <div className="card stack">
            <div className="card-title"><h3>Sound</h3></div>
            <label className="row"><input type="checkbox" checked={s.sound} onChange={(e) => s.set({ sound: e.target.checked })} /> Sounds on</label>
            <label className="row">Volume <input type="range" min={0} max={1} step={0.05} value={s.volume} onChange={(e) => s.set({ volume: Number(e.target.value) })} /> <button className="btn btn-sm" onClick={() => playSound("capture")}>Test</button></label>
          </div>
          <NarrationCard />
        </div>
        <div style={{ maxWidth: 360 }}>
          <Board fen="r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4" lastMove={["g8", "f6"]} showCoordinates={s.showCoordinates} />
        </div>
      </div>
    </div>
  );
}
