import type { CapacitorConfig } from "@capacitor/cli";

// Remote-URL mode: the store apps are thin shells that load the hosted app, so one deploy updates
// every platform and the cookie-based account works unchanged (the page is first-party on its own
// https origin, which SameSite=Lax needs). CAP_SERVER_URL is the deployed https address.
const serverUrl = process.env.CAP_SERVER_URL;
if (!serverUrl?.startsWith("https://")) throw new Error(`CAP_SERVER_URL is ${JSON.stringify(serverUrl)}: expected the deployed https address`);

const config: CapacitorConfig = {
  appId: "app.chesscoach",
  appName: "Chess Coach",
  webDir: "dist",
  server: { url: serverUrl, androidScheme: "https" },
};

export default config;
