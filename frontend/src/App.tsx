import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/shell/Shell";
import { BoardDemo } from "./pages/BoardDemo";
import { HomePage } from "./pages/HomePage";
import { PlayPage } from "./pages/PlayPage";
import { PuzzlesPage } from "./pages/PuzzlesPage";
import { OpeningsPage } from "./pages/OpeningsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { CoachPage } from "./pages/CoachPage";
import { LearnPage } from "./pages/LearnPage";
import { LessonPage } from "./pages/LessonPage";
import { GamesPage } from "./pages/GamesPage";
import { InsightsPage } from "./pages/InsightsPage";
import { EndgamesPage } from "./pages/EndgamesPage";
import { ReviewGamePage } from "./pages/ReviewGamePage";
import { ReviewPage } from "./pages/ReviewPage";
import "./styles/base.css";
import "./styles/pages.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/dev/board" element={<BoardDemo />} />
        <Route element={<Shell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/play" element={<PlayPage />} />
          <Route path="/play/:gameId" element={<PlayPage />} />
          <Route path="/puzzles" element={<PuzzlesPage />} />
          <Route path="/learn" element={<LearnPage />} />
          <Route path="/learn/:lessonId" element={<LessonPage />} />
          <Route path="/openings" element={<OpeningsPage />} />
          <Route path="/games" element={<GamesPage />} />
          <Route path="/games/:gameId" element={<GamesPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/endgames" element={<EndgamesPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/review/:gameId" element={<ReviewGamePage />} />
          <Route path="/coach" element={<CoachPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
