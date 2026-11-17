import React from "react";
import { pct } from "./api";
export default function ModelEvaluation({ model }) {
  const metrics = model.metrics?.test || model.metrics || {};
  const classes = metrics.per_class || metrics.classification_report || {};
  const shap = model.global_shap || [];
  const features = Array.isArray(shap)
    ? shap
    : Object.entries(shap).map(([feature, value]) => ({
        feature,
        mean_abs_shap: value,
      }));
  const maximum = Math.max(
    0.001,
    ...features.map((f) => Number(f.mean_abs_shap || f.importance || 0)),
  );
  const calibration =
    metrics.calibration_bins || metrics.calibration?.bins || [];
  return (
    <>
      <div className="two-columns">
        <div>
          <h3>Metrik per kelas</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Kelas</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1</th>
                </tr>
              </thead>
              <tbody>
                {["Dropout", "Enrolled", "Graduate"].map((c) => (
                  <tr key={c}>
                    <th>{c}</th>
                    <td>{classes[c]?.precision?.toFixed(3) ?? "—"}</td>
                    <td>{classes[c]?.recall?.toFixed(3) ?? "—"}</td>
                    <td>
                      {(
                        classes[c]?.f1_score ?? classes[c]?.["f1-score"]
                      )?.toFixed(3) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3>Kontribusi fitur global</h3>
          {features.slice(0, 8).map((f, i) => (
            <div className="global-feature" key={i}>
              <div>
                <span>{f.feature || f.name}</span>
                <strong>
                  {Number(f.mean_abs_shap || f.importance || 0).toFixed(3)}
                </strong>
              </div>
              <progress
                max={maximum}
                value={f.mean_abs_shap || f.importance || 0}
              />
            </div>
          ))}
          {!features.length && (
            <p className="muted small">
              Laporan SHAP global belum tersedia pada versi ini.
            </p>
          )}
        </div>
      </div>
      {calibration.length > 0 && (
        <>
          <h3>Reliability / kalibrasi</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Bin</th>
                  <th>Confidence rata-rata</th>
                  <th>Akurasi aktual</th>
                  <th>Sampel</th>
                </tr>
              </thead>
              <tbody>
                {calibration.map((b, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{pct(b.confidence ?? b.mean_predicted_probability)}</td>
                    <td>{pct(b.accuracy ?? b.fraction_of_positives)}</td>
                    <td>{b.count ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <details className="model-card">
        <summary>Model card & batas penggunaan</summary>
        <pre>{model.model_card || "Model card belum tersedia."}</pre>
      </details>
    </>
  );
}
