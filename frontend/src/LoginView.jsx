import { useState } from "react";
import { login, register } from "./api.js";

export default function LoginView({ onAuth }) {
  const [mode, setMode] = useState("login"); // login | register
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isRegister = mode === "register";

  async function onSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = isRegister
        ? await register(username.trim(), email.trim(), password)
        : await login(username.trim(), password);
      onAuth(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="intro">
        <h1>{isRegister ? "Create an account" : "Sign in"}</h1>
        <p className="lede">
          {isRegister
            ? "Citizens can report problems and follow them. Department officials are set up by an administrator."
            : "Sign in to report a problem or follow your reports. Officials see the full queue."}
        </p>
      </div>

      <form className="form auth-form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>

        {isRegister && (
          <div className="field">
            <label htmlFor="email">Email (optional)</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <p className="quiet small">Used only to tell you when a report is resolved.</p>
          </div>
        )}

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="primary" disabled={busy || !username.trim() || !password}>
          {busy ? "Please wait..." : isRegister ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="switch-mode">
        {isRegister ? "Already have an account? " : "New here? "}
        <button
          type="button"
          className="linklike"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError("");
          }}
        >
          {isRegister ? "Sign in" : "Create an account"}
        </button>
      </p>
    </div>
  );
}
