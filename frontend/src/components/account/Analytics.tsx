import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { track } from "../../lib/track";

const installedApp = () => matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

/** Records app opens, installs and page views. Renders nothing. */
export function Analytics() {
  const { pathname } = useLocation();
  useEffect(() => {
    track("app.opened", { display: installedApp() ? "standalone" : "browser" });
    const installed = () => track("app.installed", {});
    window.addEventListener("appinstalled", installed);
    return () => window.removeEventListener("appinstalled", installed);
  }, []);
  useEffect(() => track("page.viewed", { page: pathname.split("/")[1] || "home" }), [pathname]);
  return null;
}
