import { useEffect, useState } from "react";
import SubmitView from "./SubmitView.jsx";
import QueueView from "./QueueView.jsx";
import DetailView from "./DetailView.jsx";
import LoginView from "./LoginView.jsx";
import { getMe, getToken, logout, setToken, setUnauthorizedHandler } from "./api.js";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(() => Boolean(getToken()));
  const [view, setView] = useState("submit"); // submit | queue | detail
  const [selected, setSelected] = useState(null);

  function signOutLocally() {
    setToken(null);
    setUser(null);
    setView("submit");
  }

  // Restore a saved session on load, and drop it if the server rejects the token
  useEffect(() => {
    setUnauthorizedHandler(signOutLocally);
    if (!getToken()) return;
    getMe()
      .then(setUser)
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);

  function onAuth(data) {
    setToken(data.token);
    setUser(data.user);
    setView("submit");
  }

  async function signOut() {
    try {
      await logout();
    } catch {
      /* the token is dropped either way */
    }
    signOutLocally();
  }

  const openDetail = (id) => {
    setSelected(id);
    setView("detail");
  };

  if (checking) {
    return <p className="quiet wrap checking">Loading...</p>;
  }

  const official = Boolean(user?.is_official);
  const current = view === "detail" ? "queue" : view;

  return (
    <>
      <header className="site-header">
        <div className="wrap bar">
          <span className="brand">CivicSense</span>
          {user && (
            <>
              <nav aria-label="Main">
                <button
                  type="button"
                  className="tab"
                  aria-current={current === "submit" ? "page" : undefined}
                  onClick={() => setView("submit")}
                >
                  Report a problem
                </button>
                <button
                  type="button"
                  className="tab"
                  aria-current={current === "queue" ? "page" : undefined}
                  onClick={() => setView("queue")}
                >
                  {official ? "Complaints" : "My reports"}
                </button>
              </nav>
              <div className="userbox">
                <span>
                  {user.username}
                  <span className="role">{official ? "Official" : "Citizen"}</span>
                </span>
                <button type="button" className="linklike" onClick={signOut}>
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </header>
      <main className="wrap">
        {!user && <LoginView onAuth={onAuth} />}
        {user && view === "submit" && <SubmitView />}
        {user && view === "queue" && <QueueView official={official} onOpen={openDetail} />}
        {user && view === "detail" && (
          <DetailView id={selected} official={official} onBack={() => setView("queue")} />
        )}
      </main>
    </>
  );
}
