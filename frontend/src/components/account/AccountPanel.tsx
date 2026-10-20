import { useEffect, useRef, useState } from "react";
import { api, type Account } from "../../lib/api";

interface GoogleIdentity {
  initialize(options: { client_id: string; callback: (response: { credential: string }) => void }): void;
  renderButton(parent: HTMLElement, options: Record<string, string>): void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleIdentity } } }
}

const GOOGLE_SCRIPT = "https://accounts.google.com/gsi/client";

/** The player's account: Google sign-in for a guest, sign-out, and deleting everything stored. */
export function AccountPanel() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const googleButton = useRef<HTMLDivElement>(null);
  const fail = (e: Error) => setError(e.message);

  useEffect(() => { api.account().then(setAccount, fail); }, []);

  useEffect(() => {
    const clientId = account?.google_client_id;
    const parent = googleButton.current;
    if (!clientId || account.email || !parent) return;
    const render = () => {
      window.google!.accounts.id.initialize({
        client_id: clientId,
        callback: ({ credential }) => api.signInWithGoogle(credential).then(() => location.reload(), fail), // the player may change: reload everything
      });
      window.google!.accounts.id.renderButton(parent, { theme: "outline", size: "large", text: "signin_with" });
    };
    if (window.google) return render();
    const script = document.createElement("script");
    script.src = GOOGLE_SCRIPT;
    script.async = true;
    script.onload = render;
    script.onerror = () => setError("Google sign-in could not load. Check the connection and reload.");
    document.head.appendChild(script);
  }, [account]);

  const deleteData = () => {
    if (confirm("Delete your games, reviews, puzzle results and lesson progress from this server? This cannot be undone.")) {
      api.deleteAccount().then(() => location.reload(), fail);
    }
  };

  return (
    <div className="card stack" data-testid="account">
      <div className="card-title"><h3>Account</h3></div>
      {account?.email ? (
        <>
          <p>Signed in as <strong>{account.email}</strong>. Your progress follows you to every device where you sign in.</p>
          <div className="row"><button className="btn btn-sm" onClick={() => api.signOut().then(() => location.reload(), fail)}>Sign out</button></div>
        </>
      ) : (
        <>
          <p className="muted">You play as a guest: your progress is kept for this browser.{account?.google_client_id && " Sign in to keep it on every device. Signing in stores your email address."}</p>
          <div ref={googleButton} />
        </>
      )}
      <div className="row"><button className="btn btn-sm btn-danger" onClick={deleteData} data-testid="delete-account">Delete my data</button></div>
      {error && <p className="muted" role="alert">{error}</p>}
    </div>
  );
}
