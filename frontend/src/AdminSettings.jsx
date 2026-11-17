import React, { useEffect, useState } from "react";
import { api, post, list } from "./api";
export default function AdminSettings() {
  const [thresholds, setThresholds] = useState(null),
    [reason, setReason] = useState(""),
    [message, setMessage] = useState(""),
    [references, setReferences] = useState([]),
    [reference, setReference] = useState({ feature: "", code: "", label: "" });
  useEffect(() => {
    api("/admin/thresholds")
      .then(setThresholds)
      .catch((e) => setMessage(e.message));
    api("/admin/references")
      .then((d) => setReferences(list(d, "references")))
      .catch((e) => setMessage(e.message));
  }, []);
  async function save(e) {
    e.preventDefault();
    try {
      const d = await post("/admin/thresholds", {
        medium: Number(thresholds.medium),
        high: Number(thresholds.high),
        reason,
      });
      setThresholds(d);
      setMessage(
        "Threshold berversi tersimpan. Prediksi historis tidak berubah.",
      );
    } catch (e) {
      setMessage(e.message);
    }
  }
  async function relabel(e) {
    e.preventDefault();
    try {
      await api("/admin/references", {
        method: "PUT",
        body: JSON.stringify(reference),
      });
      setMessage("Label referensi tersimpan; kode model tidak berubah.");
    } catch (e) {
      setMessage(e.message);
    }
  }
  return (
    <>
      <div className="two-columns">
        <form className="panel padded" onSubmit={save}>
          <h2>Aturan risiko</h2>
          <p className="muted small">
            Perubahan hanya berlaku pada prediksi baru.
          </p>
          {thresholds && (
            <>
              <label>
                Batas risiko sedang
                <input
                  required
                  type="number"
                  min="0.01"
                  max="0.98"
                  step="0.01"
                  value={thresholds.medium}
                  onChange={(e) =>
                    setThresholds({ ...thresholds, medium: e.target.value })
                  }
                />
              </label>
              <label>
                Batas risiko tinggi
                <input
                  required
                  type="number"
                  min="0.02"
                  max="0.99"
                  step="0.01"
                  value={thresholds.high}
                  onChange={(e) =>
                    setThresholds({ ...thresholds, high: e.target.value })
                  }
                />
              </label>
              <label>
                Alasan perubahan
                <textarea
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <button className="primary">Simpan versi aturan</button>
            </>
          )}
        </form>
        <form className="panel padded" onSubmit={relabel}>
          <h2>Label referensi</h2>
          <p className="muted small">
            Ubah label tampilan tanpa mengubah kode kategori dataset.
          </p>
          <label>
            Nama fitur
            <input
              required
              list="reference-features"
              value={reference.feature}
              onChange={(e) =>
                setReference({ ...reference, feature: e.target.value })
              }
            />
            <datalist id="reference-features">
              {[...new Set(references.map((r) => r.feature))].map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </label>
          <label>
            Kode kategori
            <input
              required
              type="number"
              step="1"
              value={reference.code}
              onChange={(e) =>
                setReference({ ...reference, code: e.target.value })
              }
            />
          </label>
          <label>
            Label tampilan
            <input
              required
              value={reference.label}
              onChange={(e) =>
                setReference({ ...reference, label: e.target.value })
              }
            />
          </label>
          <button className="primary">Simpan label</button>
        </form>
      </div>
      {message && (
        <p className="error" role="status">
          {message}
        </p>
      )}
    </>
  );
}
