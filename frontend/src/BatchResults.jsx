import React, { useState } from "react";
import { pct } from "./api";
export default function BatchResults({ job }) {
  const [risk, setRisk] = useState("");
  const results = (job.results || []).filter(
    (r) => !risk || (r.prediction || r).risk_band === risk,
  );
  return (
    <>
      <div className="actions">
        {job.errors?.length > 0 && (
          <a
            className="button"
            href={`/api/batch-jobs/${job.id}/export?errors=1`}
          >
            Unduh error CSV
          </a>
        )}
      </div>
      {job.preview?.length > 0 && (
        <details className="model-card">
          <summary>Preview data ({job.preview.length} baris)</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Baris</th>
                  <th>ID mahasiswa</th>
                  <th>Tahap</th>
                  <th>Tanggal</th>
                </tr>
              </thead>
              <tbody>
                {job.preview.map((r, i) => (
                  <tr key={i}>
                    <td>{r.row || i + 2}</td>
                    <td>{r.student_id || r.metadata?.student_id}</td>
                    <td>{r.stage || r.prediction_stage}</td>
                    <td>{r.snapshot_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {job.results?.length > 0 && (
        <>
          <h3>Hasil batch</h3>
          <label>
            Tingkat risiko
            <select value={risk} onChange={(e) => setRisk(e.target.value)}>
              <option value="">Semua risiko</option>
              <option value="high">Tinggi</option>
              <option value="medium">Sedang</option>
              <option value="low">Rendah</option>
            </select>
          </label>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mahasiswa</th>
                  <th>Kelas</th>
                  <th>P(Dropout)</th>
                  <th>Risiko</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => {
                  const r = row.prediction || row;
                  return (
                    <tr key={i}>
                      <td>{r.student_id}</td>
                      <td>{r.predicted_class}</td>
                      <td>{pct(r.probabilities?.Dropout ?? r.p_dropout)}</td>
                      <td>{r.risk_band}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
