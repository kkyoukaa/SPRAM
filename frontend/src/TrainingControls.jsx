import React, { useState } from "react";
import { api, post, pct } from "./api";
export default function TrainingControls({ model }) {
  const [schema, setSchema] = useState(null),
    [values, setValues] = useState(""),
    [result, setResult] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function open() {
    try {
      const d = await api(`/admin/model-versions/${model.id}`);
      setSchema(d.schema || d.feature_schema);
      setValues(
        JSON.stringify((d.schema || d.feature_schema)?.example || {}, null, 2),
      );
    } catch (e) {
      setError(e.message);
    }
  }
  async function run(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const features = JSON.parse(values);
      setResult(
        await post("/admin/sandbox/predict", {
          model_version: model.id,
          features,
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="sandbox">
      <h3>Sandbox Admin</h3>
      <p className="muted small">
        Uji kandidat tanpa menyimpan hasil ke dashboard dosen. Model
        experimental hanya tersedia di sini.
      </p>
      <button onClick={open}>Buka sandbox model ini</button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {schema && (
        <form onSubmit={run}>
          <label>
            Input fitur JSON
            <textarea
              className="json-input"
              value={values}
              onChange={(e) => setValues(e.target.value)}
              required
              spellCheck="false"
            />
          </label>
          <button className="primary" disabled={busy}>
            {busy ? "Menghitung…" : "Uji kandidat"}
          </button>
        </form>
      )}
      {result && (
        <div className="assistant-answer">
          <strong>{result.predicted_class}</strong>
          <p>
            {["Dropout", "Enrolled", "Graduate"]
              .map((c) => `${c}: ${pct(result.probabilities?.[c])}`)
              .join(" · ")}
          </p>
          <p className="muted small">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
