import { useState } from "react";
import SubmitView from "./SubmitView.jsx";
import QueueView from "./QueueView.jsx";
import DetailView from "./DetailView.jsx";

export default function App() {
  const [view, setView] = useState("submit"); // submit | queue | detail
  const [selected, setSelected] = useState(null);

  const openDetail = (id) => {
    setSelected(id);
    setView("detail");
  };
  const current = view === "detail" ? "queue" : view;

  return (
    <>
      <header className="site-header">
        <div className="wrap bar">
          <span className="brand">CivicSense</span>
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
              Complaints
            </button>
          </nav>
        </div>
      </header>
      <main className="wrap">
        {view === "submit" && <SubmitView />}
        {view === "queue" && <QueueView onOpen={openDetail} />}
        {view === "detail" && (
          <DetailView id={selected} onBack={() => setView("queue")} />
        )}
      </main>
    </>
  );
}