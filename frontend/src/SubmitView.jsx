import { useEffect, useState } from "react";
import { submitComplaint } from "./api.js";

const labelFor = (category) =>
  category
    ? category.charAt(0).toUpperCase() + category.slice(1).replace(/_/g, " ")
    : "";

function Decision({ data, onReset }) {
  if (data.status === "needs_details") {
    return (
      <section className="decision" aria-live="polite">
        <h2>We need more detail</h2>
        <p>
          We could not tell what the problem is from your description. Say what
          is damaged or broken and where it is, then submit again.
        </p>
      </section>
    );
  }

  if (data.status === "duplicate") {
    return (
      <section className="decision" aria-live="polite">
        <p className="ref">Reference {data.ref}</p>
        <h2>Already reported</h2>
        <p>
          This matches report {data.duplicate_of}. Your report was added to it
          as a supporting report, so no new letter was needed.
        </p>
        <button type="button" className="secondary" onClick={onReset}>
          Report another problem
        </button>
      </section>
    );
  }

  return (
    <section className="decision" aria-live="polite">
      <p className="ref">Reference {data.ref}</p>
      <h2>Sent to {data.department}</h2>
      <dl className="facts">
        <div>
          <dt>Desk</dt>
          <dd>{data.desk}</dd>
        </div>
        <div>
          <dt>Respond within</dt>
          <dd>{data.sla_hours} hours</dd>
        </div>
        <div>
          <dt>Problem</dt>
          <dd>{labelFor(data.category)}</dd>
        </div>
        <div>
          <dt>Severity</dt>
          <dd>
            <span className={`sev sev-${data.severity}`}>{data.severity}</span>
          </dd>
        </div>
      </dl>

      <h3>Why this desk</h3>
      <p className="quiet">This desk handles: {data.rule}</p>

      <h3>Complaint letter</h3>
      <pre className="letter">{data.letter}</pre>

      <button type="button" className="secondary" onClick={onReset}>
        Report another problem
      </button>
    </section>
  );
}

export default function SubmitView() {
  const [text, setText] = useState("");
  const [location, setLocation] = useState("");
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!photo) {
      setPreview("");
      return undefined;
    }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  async function onSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await submitComplaint({ text, location, photo }));
    } catch (err) {
      setResult(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setText("");
    setLocation("");
    setPhoto(null);
    setResult(null);
    setError("");
  }

  return (
    <>
      <div className="intro">
        <h1>Report a civic problem</h1>
        <p className="lede">
          Describe the problem and add a photo if you have one. We send it to
          the department that handles it and set a deadline for a response.
        </p>
      </div>

      <div className="layout">
        <form className="form" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="text">What is the problem?</label>
            <textarea
              id="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Deep pothole near the school gate"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="location">Where is it?</label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Street, area, nearest landmark"
            />
          </div>

          <div className="field">
            <label htmlFor="photo">Photo (optional)</label>
            <input
              id="photo"
              type="file"
              accept="image/*"
              onChange={(e) => setPhoto(e.target.files[0] ?? null)}
            />
            {preview && <img className="preview" src={preview} alt="Selected photo" />}
          </div>

          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="primary" disabled={busy || !text.trim()}>
            {busy ? "Submitting..." : "Submit report"}
          </button>
        </form>

        <div>
          {result ? (
            <Decision data={result} onReset={reset} />
          ) : (
            <section className="next">
              <h2>What happens next</h2>
              <ol>
                <li>We read your description and photo and work out what the problem is.</li>
                <li>We check whether someone has already reported the same problem at the same place.</li>
                <li>We send it to the right department and desk, write the complaint letter and set a deadline.</li>
              </ol>
            </section>
          )}
        </div>
      </div>
    </>
  );
}