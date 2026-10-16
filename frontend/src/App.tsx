import { BrowserRouter, Route, Routes } from "react-router-dom";
import { BoardDemo } from "./pages/BoardDemo";
import { useSettings } from "./store/settings";
import "./styles/base.css";

function Shell({ children }: { children: React.ReactNode }) {
  const boardTheme = useSettings((s) => s.boardTheme);
  return <div data-board={boardTheme} style={{ minHeight: "100%" }}>{children}</div>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/dev/board" element={<BoardDemo />} />
          <Route path="*" element={<BoardDemo />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
