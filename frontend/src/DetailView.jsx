import { useEffect, useState } from "react";
import { getComplaint, resolveComplaint } from "./api.js";
import { followUpText, labelFor } from "./labels.js";

function parseLine(line) {
  const match = /^\[hour\s+(\d+)\]\s*(.*)$/.exec(line);
  return match ? { hour: match[1], text: match[2] } : { hour: "", text: line };
}

export default function DetailView({ id, official, onBack }) {
  const [c, setC] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getComplaint(id).then(setC).catch((e) => setError(e.message));
  }, [id]);

  async function resolve() {
    setBusy(true);
    setError("");
    try {
      setC(await resolveComplaint(id));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!c) {
    return (
      <>
        <button type="button" className="secondary back" onClick={onBack}>
          Back to the list
        </button>
        {error ? (
          <p className="error" role="alert">{error}</p>
        ) : (
          <p className="quiet">Loading complaint...</p>
        )}
      </>
    );
  }

  const routed = c.status === "routed";
  const history = (c.fu_history ?? []).map(parseLine);

  return (
    <div className="detail">
      <div>
        <button type="button" className="secondary back" onClick={onBack}>
          Back to the list
        </button>
      </div>

      <header>
        <p className="ref">Reference {c.ref}</p>
        <h1>{labelFor(c.category) || "Unclassified report"}</h1>
        <p className="quiet">{followUpText(c)}</p>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      {routed && (
        <section className="panel">
          <dl className="facts">
            <div><dt>Department</dt><dd>{c.department}</dd></div>
            <div><dt>Desk</dt><dd>{c.desk}</dd></div>
            <div><dt>Respond within</dt><dd>{c.sla_hours} hours</dd></div>
            <div>
              <dt>Severity</dt>
              <dd><span className={`sev sev-${c.severity}`}>{c.severity}</span></dd>
            </div>
          </dl>
          {official && c.fu_status === "open" && (
            <button type="button" className="primary" onClick={resolve} disabled={busy}>
              {busy ? "Saving..." : "Mark as resolved"}
            </button>
          )}
        </section>
      )}

      {c.status === "duplicate" && (
        <section className="panel">
          <h2>Supporting report</h2>
          <p className="quiet">
            This report was matched to {c.duplicate_of}, an earlier report of the
            same problem at the same place.
          </p>
        </section>
      )}

      <section className="panel">
        <h2>What was reported</h2>
        <p className="body-text">{c.text}</p>
        <p className="quiet">Location: {c.location || "Not given"}</p>
        {c.latitude != null && (
          <p className="quiet">
            GPS: {c.latitude.toFixed(5)}, {c.longitude.toFixed(5)} (
            {c.gps_source === "photo" ? "from the photo" : "from the device"}){" "}
            <a
              href={`https://www.openstreetmap.org/?mlat=${c.latitude}&mlon=${c.longitude}#map=18/${c.latitude}/${c.longitude}`}
              target="_blank"
              rel="noreferrer"
            >
              Open map
            </a>
          </p>
        )}
        {c.photo && (
          <img className="preview" src={c.photo} alt="Photo submitted with the report" />
        )}
        {c.reason && (
          <>
            <h3>Assessment</h3>
            <p className="quiet">{c.reason}</p>
          </>
        )}
        {c.rule && (
          <>
            <h3>Why this desk</h3>
            <p className="quiet">This desk handles: {c.rule}</p>
          </>
        )}
      </section>

      {routed && history.length > 0 && (
        <section className="panel">
          <h2>Follow-up</h2>
          <p className="quiet small">Hours are counted from when the report was filed.</p>
          <ul className="timeline">
            {history.map((h, i) => (
              <li key={i}>
                <span className="when">{h.hour ? `Hour ${h.hour}` : ""}</span>
                <span>{h.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {c.letter && (
        <section className="panel">
          <h2>Complaint letter</h2>
          <pre className="letter">{c.letter}</pre>
        </section>
      )}
    </div>
  );
}