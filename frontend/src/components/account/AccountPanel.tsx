import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Account } from "../../lib/api";

interface GoogleIdentity {
  initialize(options: { client_id: string; callback: (response: { credential: string }) => void }): void;
  renderButton(parent: HTMLElement, options: Record<string, string>): void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleIdentity } } }
}

const GOOGLE_SCRIPT = "https://accounts.google.com/gsi/client";

/** The player's account: email + password or Google sign-in for a guest; sign-out, a new password and deleting everything for an account. */
export function AccountPanel() {
  const [account, setAccount] = useState<Account | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [current, setCurrent] = useState("");
  const googleButton = useRef<HTMLDivElement>(null);
  const fail = (e: Error) => setNotice(e.message);
  const resetToken = new URLSearchParams(location.search).get("reset");

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
    script.onerror = () => setNotice("Google sign-in could not load. Check the connection and reload.");
    document.head.appendChild(script);
  }, [account]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    (mode === "signup" ? api.signUp : api.signIn)(email, password).then(() => location.reload(), fail);
  };
  const forgot = () => {
    if (!email) return setNotice("Type your email first.");
    api.requestReset(email).then(() => setNotice("If that address has an account, a reset link is on its way."), fail);
  };
  const confirmReset = (e: FormEvent) => {
    e.preventDefault();
    api.confirmReset(resetToken!, password).then(() => location.assign("/settings"), fail);
  };
  const changePassword = (e: FormEvent) => {
    e.preventDefault();
    api.changePassword(current, password).then(() => { setCurrent(""); setPassword(""); setNotice("Password changed. Other devices are signed out."); }, fail);
  };
  const deleteData = () => {
    if (confirm("Delete your games, reviews, puzzle results and lesson progress from this server? This cannot be undone.")) {
      api.deleteAccount().then(() => location.reload(), fail);
    }
  };

  return (
    <div className="card stack" data-testid="account">
      <div className="card-title"><h3>Account</h3></div>
      {resetToken ? (
        <form className="stack" onSubmit={confirmReset}>
          <p>Choose a new password.</p>
          <input className="input" type="password" autoComplete="new-password" placeholder="New password (8+ characters)" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="row"><button className="btn btn-primary" type="submit">Set password</button></div>
        </form>
      ) : account?.email ? (
        <>
          <p>Signed in as <strong>{account.email}</strong>. Your progress follows you to every device where you sign in.</p>
          <div className="row">
            <button className="btn btn-sm" onClick={() => api.signOut().then(() => location.reload(), fail)}>Sign out</button>
            <button className="btn btn-sm" onClick={() => api.signOut(true).then(() => location.reload(), fail)}>Sign out everywhere</button>
          </div>
          {account.has_password && (
            <form className="row" style={{ flexWrap: "wrap" }} onSubmit={changePassword}>
              <input className="input" style={{ width: 180 }} type="password" autoComplete="current-password" placeholder="Current password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
              <input className="input" style={{ width: 180 }} type="password" autoComplete="new-password" placeholder="New password (8+)" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
              <button className="btn btn-sm" type="submit">Change password</button>
            </form>
          )}
        </>
      ) : (
        <>
          <p className="muted">You play as a guest: your progress is kept for this browser. Sign in to keep it on every device. Signing in stores your email address.</p>
          <form className="stack" onSubmit={submit} data-testid="account-form">
            <input className="input" type="email" autoComplete="email" placeholder="Email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className="input" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder={mode === "signup" ? "Password (8+ characters)" : "Password"} minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button className="btn btn-primary" type="submit">{mode === "signup" ? "Create account" : "Sign in"}</button>
              <button className="btn btn-ghost btn-sm" type="button" onClick={() => setMode(mode === "signup" ? "signin" : "signup")}>
                {mode === "signup" ? "I have an account" : "Create an account"}
              </button>
              {mode === "signin" && <button className="btn btn-ghost btn-sm" type="button" onClick={forgot}>Forgot password?</button>}
            </div>
          </form>
          <div ref={googleButton} />
        </>
      )}
      <div className="row"><button className="btn btn-sm btn-danger" onClick={deleteData} data-testid="delete-account">Delete my data</button></div>
      {notice && <p className="muted" role="alert">{notice}</p>}
    </div>
  );
}
