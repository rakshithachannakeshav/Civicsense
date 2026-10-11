import { useEffect, useMemo, useState } from "react";
import { listComplaints } from "./api.js";
import { followUpText, labelFor, timeAgo } from "./labels.js";

const FILTERS = [
  { id: "open", label: "Open",
    test: (c) => c.status === "routed" && c.fu_status !== "closed" },
  { id: "closed", label: "Closed",
    test: (c) => c.status === "routed" && c.fu_status === "closed" },
  { id: "duplicate", label: "Duplicates", test: (c) => c.status === "duplicate" },
  { id: "needs_details", label: "Needs details", test: (c) => c.status === "needs_details" },
  { id: "all", label: "All", test: () => true },
];

const SEVERITY_RANK = { high: 3, medium: 2, low: 1 };

// Higher number means more urgent
function urgency(c) {
  if (c.fu_status === "critical") return 1000;
  return c.fu_level * 100 + (SEVERITY_RANK[c.severity] ?? 0) * 10;
}

function stateClass(c) {
  if (c.fu_status === "critical") return "state-critical";
  if (c.status === "routed" && c.fu_level > 0 && c.fu_status !== "closed") {
    return "state-escalated";
  }
  return "";
}

export default function QueueView({ onOpen }) {
  const [complaints, setComplaints] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("open");

  function load() {
    setError("");
    listComplaints().then(setComplaints).catch((e) => setError(e.message));
  }

  useEffect(() => {
    load();
  }, []);

  // How many duplicate reports each original has received
  const extraReports = useMemo(() => {
    const counts = {};
    (complaints ?? []).forEach((c) => {
      if (c.status === "duplicate") counts[c.duplicate_of] = (counts[c.duplicate_of] ?? 0) + 1;
    });
    return counts;
  }, [complaints]);

  const rows = useMemo(() => {
    const active = FILTERS.find((f) => f.id === filter);
    const list = (complaints ?? []).filter(active.test);
    if (filter === "open") {
      list.sort(
        (a, b) =>
          urgency(b) - urgency(a) || new Date(a.created_at) - new Date(b.created_at)
      );
    }
    return list;
  }, [complaints, filter]);

  return (
    <>
      <div className="intro">
        <h1>Complaints</h1>
        <p className="lede">
          Open complaints are listed with the most urgent first: critical and
          escalated complaints, then by severity.
        </p>
      </div>

      <div className="toolbar">
        <div className="seg" role="group" aria-label="Filter complaints">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button type="button" className="secondary refresh" onClick={load}>
          Refresh
        </button>
      </div>

      {error && (
        <p className="error" role="alert">
          Could not load complaints: {error}
        </p>
      )}
      {complaints === null && !error && <p className="quiet">Loading complaints...</p>}
      {complaints !== null && rows.length === 0 && (
        <p className="quiet empty">
          Nothing here yet. Reports sent from "Report a problem" appear in this list.
        </p>
      )}

      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Reference</th>
                <th>Problem</th>
                <th>Location</th>
                <th>Handled by</th>
                <th>Severity</th>
                <th>Follow-up</th>
                <th>Reported</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>
                    <button type="button" className="linklike" onClick={() => onOpen(c.id)}>
                      {c.ref}
                    </button>
                  </td>
                  <td>
                    <div>{labelFor(c.category) || "Unclassified"}</div>
                    <div className="quiet small">
                      {c.text.length > 70 ? `${c.text.slice(0, 70)}...` : c.text}
                    </div>
                    {extraReports[c.ref] > 0 && (
                      <div className="small extra">
                        {extraReports[c.ref]} more {extraReports[c.ref] === 1 ? "report" : "reports"}
                      </div>
                    )}
                  </td>
                  <td>{c.location || "Not given"}</td>
                  <td>
                    {c.status === "routed" ? (
                      <>
                        <div>{c.department}</div>
                        <div className="quiet small">{c.desk}</div>
                      </>
                    ) : (
                      "Not routed"
                    )}
                  </td>
                  <td>
                    {c.severity ? (
                      <span className={`sev sev-${c.severity}`}>{c.severity}</span>
                    ) : (
                      "None"
                    )}
                  </td>
                  <td className={stateClass(c)}>{followUpText(c)}</td>
                  <td className="quiet">{timeAgo(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}