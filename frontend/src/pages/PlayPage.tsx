import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BotPicker } from "../components/play/BotPicker";
import { GameView } from "../components/play/GameView";
import { api, type BotPublic, type GameState } from "../lib/api";
import { useEngine } from "../store/engine";

export function PlayPage() {
  const { gameId } = useParams();
  const navigate = useNavigate();
  const [game, setGame] = useState<GameState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadEngine = useEngine((s) => s.load);

  useEffect(() => { void loadEngine(); }, [loadEngine]);

  useEffect(() => {
    if (!gameId) { setGame(null); return; }
    api.game(gameId).then(setGame).catch((e: Error) => setError(e.message));
  }, [gameId]);

  const start = async (bot: Pick<BotPublic, "id">, color: "white" | "black" | "random", coach: boolean, tc: string | null = null) => {
    setBusy(true);
    setError(null);
    try {
      const g = await api.newGame(bot.id, color, coach || bot.id === "coach", tc);
      setGame(g);
      navigate(`/play/${g.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (gameId && game) {
    return (
      <GameView
        key={game.id}
        initial={game}
        onNewGame={() => navigate("/play")}
        onRematch={() => start(game.bot, game.player_color, game.coach_mode, game.time_control)}
      />
    );
  }
  if (gameId && !game) return <p className="faint">{error ?? "Loading game…"}</p>;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Play a bot</h1>
          <p>Twenty opponents from beginner to engine, each with a style. Every game can be reviewed.</p>
        </div>
      </div>
      {error && <div className="chip chip-danger" style={{ marginBottom: 12 }}>{error}</div>}
      <BotPicker onStart={start} busy={busy} />
    </>
  );
}
