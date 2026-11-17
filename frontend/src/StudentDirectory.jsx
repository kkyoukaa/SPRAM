import React, { useEffect, useState } from "react";
import { api, post, list, pct } from "./api";
import { Search, ChevronLeft, ChevronRight, UserCheck } from "lucide-react";

const stageName = (v) => (v === "academic_update" ? "Academic update" : v === "intake" ? "Intake" : "Belum tersedia");
const RISK = { high: "Tinggi", medium: "Sedang", low: "Rendah" };

export default function StudentDirectory({ onStudent, user }) {
  const [q, setQ] = useState(""), [search, setSearch] = useState("");
  const [risk, setRisk] = useState(""), [handling, setHandling] = useState("");
  const [prediction, setPrediction] = useState(""), [page, setPage] = useState(1);
  const [data, setData] = useState(null), [error, setError] = useState(""), [tick, setTick] = useState(0);
  const [selected, setSelected] = useState([]), [advisors, setAdvisors] = useState([]);
  const [advisorId, setAdvisorId] = useState(""), [message, setMessage] = useState("");
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(q);
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ q: search, risk_band: risk, handling, prediction_class: prediction });
    api(`/students?${params}`)
      .then((d) => active && (setData(d), setError("")))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [search, risk, handling, prediction, tick]);
  useEffect(() => {
    if (isAdmin) api("/admin/users").then((d) => setAdvisors(list(d, "items").filter((u) => u.role === "advisor"))).catch(() => {});
  }, [isAdmin]);

  const rows = list(data, "items");
  const pages = Math.max(1, Math.ceil(rows.length / 25));
  const view = rows.slice((page - 1) * 25, page * 25);
  const toggle = (sid) =>
    setSelected(selected.includes(sid) ? selected.filter((x) => x !== sid) : [...selected, sid]);

  async function assign() {
    setError("");
    setMessage("");
    try {
      const r = await post("/admin/assignments", { advisor_id: Number(advisorId), student_ids: selected });
      setMessage(`${r.count} mahasiswa ditetapkan ke dosen wali.`);
      setSelected([]);
      setTick((t) => t + 1);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">DATA MAHASISWA</span>
          <h1>Mahasiswa</h1>
          <p>Informasi utama, risiko model, dan status penanganan dalam satu daftar.</p>
        </div>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {message && (
        <div role="status" className="success">
          {message}
        </div>
      )}
      <section className="panel student-directory">
        <div className="toolbar">
          <div className="search">
            <Search size={18} />
            <input
              aria-label="Cari mahasiswa"
              placeholder="Cari ID mahasiswa atau kode program…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <span className="muted">{rows.length} mahasiswa</span>
        </div>
        <div className="filter-row">
          <label>
            Hasil prediksi
            <select
              value={prediction}
              onChange={(e) => {
                setPrediction(e.target.value);
                setPage(1);
              }}
              aria-label="Hasil prediksi"
            >
              <option value="">Semua hasil</option>
              <option value="Dropout">Putus kuliah</option>
              <option value="Enrolled">Masih aktif</option>
              <option value="Graduate">Lulus</option>
            </select>
          </label>
          <label>
            Risiko
            <select
              value={risk}
              onChange={(e) => {
                setRisk(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Semua risiko</option>
              <option value="high">Tinggi</option>
              <option value="medium">Sedang</option>
              <option value="low">Rendah</option>
            </select>
          </label>
          <label>
            Penanganan
            <select
              value={handling}
              onChange={(e) => {
                setHandling(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Semua status</option>
              <option value="belum">Belum ditangani</option>
              <option value="dijadwalkan">Dijadwalkan</option>
              <option value="konseling">Sudah konseling</option>
              <option value="dipantau">Dipantau</option>
              <option value="selesai">Penanganan selesai</option>
            </select>
          </label>
        </div>
        {isAdmin && selected.length > 0 && (
          <div className="assign-bar">
            <UserCheck size={17} />
            <span>{selected.length} mahasiswa dipilih</span>
            <select value={advisorId} onChange={(e) => setAdvisorId(e.target.value)} aria-label="Dosen wali">
              <option value="">Pilih dosen wali…</option>
              {advisors.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <button className="primary" disabled={!advisorId} onClick={assign}>
              Tetapkan
            </button>
            <button onClick={() => setSelected([])}>Batal</button>
          </div>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {isAdmin && <th aria-label="Pilih" />}
                <th>ID Mahasiswa</th>
                <th>Informasi utama</th>
                <th>Dosen wali</th>
                <th>Hasil prediksi</th>
                <th>Peluang putus kuliah</th>
                <th>Risiko</th>
                <th>Penanganan</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {view.map((s, i) => {
                const p = s.latest_prediction || {};
                return (
                  <tr key={s.student_id || i}>
                    {isAdmin && (
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Pilih ${s.student_id}`}
                          checked={selected.includes(s.student_id)}
                          onChange={() => toggle(s.student_id)}
                        />
                      </td>
                    )}
                    <td>
                      <strong>{s.student_id}</strong>
                      <small>{stageName(p.stage)}</small>
                    </td>
                    <td>
                      <span>{s.info?.program || "Program belum tersedia"}</span>
                      <small>
                        Usia saat mendaftar {s.info?.age || "—"} · {s.info?.gender || "—"}
                      </small>
                    </td>
                    <td>{s.advisor_name || <span className="muted">Belum di-assign</span>}</td>
                    <td>{p.predicted_class ? { Dropout: "Putus kuliah", Enrolled: "Masih aktif", Graduate: "Lulus" }[p.predicted_class] : "Belum diprediksi"}</td>
                    <td className="number">{p.probabilities ? pct(p.probabilities.Dropout) : "—"}</td>
                    <td>
                      {p.risk_band ? (
                        <span className={`badge ${p.risk_band}`}>Risiko: {RISK[p.risk_band]}</span>
                      ) : (
                        <span className="muted small">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge handling ${s.handling?.status || "belum"}`}>
                        {s.handling?.label || "Belum ditangani"}
                      </span>
                    </td>
                    <td>
                      <button onClick={() => onStudent(s.student_id)}>
                        Lihat detail <ChevronRight size={15} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!view.length && (
            <div className="empty">
              <p>Data mahasiswa tidak ditemukan.</p>
            </div>
          )}
        </div>
        <div className="pagination">
          <span>
            Halaman {page} / {pages}
          </span>
          <div>
            <button aria-label="Halaman sebelumnya" disabled={page === 1} onClick={() => setPage(page - 1)}>
              <ChevronLeft size={16} />
            </button>
            <button aria-label="Halaman berikutnya" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
