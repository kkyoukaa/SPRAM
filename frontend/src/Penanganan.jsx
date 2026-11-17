import React, { useEffect, useState } from "react";
import { AlertCircle, ClipboardList, ShieldAlert, Users } from "lucide-react";
import { api, list } from "./api";
import {
  AdvisorAssistant,
  Consultation,
  Handling,
  Note,
  RiskSummary,
  Factors,
  HistoryPanel,
} from "./StudentDetail";

const RISK_TEXT = { high: "Risiko tinggi", medium: "Risiko sedang", low: "Risiko rendah" };

export default function Penanganan({ initialStudent, user }) {
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(initialStudent || "");
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    api("/students")
      .then((d) => {
        if (!alive) return;
        const items = list(d, "items");
        setStudents(items);
        if (!selected && items.length) setSelected(items[0].student_id);
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [tick]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let alive = true;
    setError("");
    setDetail(null);
    api(`/students/${encodeURIComponent(selected)}/detail`)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [selected, tick]);

  const reload = () => setTick((t) => t + 1);
  const current = students.find((s) => s.student_id === selected);

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PENANGANAN</span>
          <h1>Ruang penanganan</h1>
          <p>
            Rekomendasi, konsultasi terpandu, dan status penanganan untuk
            mahasiswa bimbingan Anda.
          </p>
        </div>
        <span className="badge">
          <Users size={14} /> {students.length} mahasiswa
        </span>
      </div>

      {error && (
        <div className="error" role="alert">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      {!students.length ? (
        <section className="panel padded">
          <h2>Belum ada mahasiswa bimbingan</h2>
          <p className="muted">
            Admin belum menetapkan mahasiswa kepada Anda. Penanganan hanya
            tersedia untuk mahasiswa yang sudah ditetapkan.
          </p>
        </section>
      ) : (
        <div className="handling-workspace">
          <section className="panel padded handling-picker">
            <h2>Pilih mahasiswa</h2>
            <ul className="handling-list">
              {students.map((s) => {
                const risk = s.latest_prediction?.risk_band;
                const handling = s.handling?.label || "Belum ditangani";
                return (
                  <li key={s.student_id}>
                    <button
                      type="button"
                      className={`handling-item ${selected === s.student_id ? "selected" : ""}`}
                      onClick={() => setSelected(s.student_id)}
                    >
                      <span className="handling-id">{s.student_id}</span>
                      <span className="handling-meta">
                        <span className={`badge ${risk || ""}`}>
                          <ShieldAlert size={12} /> {RISK_TEXT[risk] || "Belum diprediksi"}
                        </span>
                        <span className="muted small">{handling}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <div className="handling-main">
            {!selected && (
              <section className="panel padded">
                <p className="muted">Pilih satu mahasiswa untuk mulai menangani.</p>
              </section>
            )}
            {selected && !detail && !error && (
              <section className="panel padded">Memuat data mahasiswa…</section>
            )}
            {selected && detail && (
              <>
                <section className="panel padded">
                  <div className="panel-title">
                    <div>
                      <span className="eyebrow">MAHASISWA</span>
                      <h2>{selected}</h2>
                      <p className="muted small">
                        {current?.info?.program || "Program studi —"} ·{" "}
                        {current?.info?.age || "—"} tahun ·{" "}
                        {current?.info?.gender || "—"}
                      </p>
                    </div>
                    <span className="badge handling">
                      <ClipboardList size={14} />{" "}
                      {detail.case?.status_label || "Belum ditangani"}
                    </span>
                  </div>
                  {detail.prediction ? (
                    <RiskSummary data={detail} />
                  ) : (
                    <Note>
                      Mahasiswa ini belum memiliki hasil prediksi. Rekomendasi
                      dan chatbot belum tersedia sampai ada prediksi.
                    </Note>
                  )}
                </section>

                {detail.prediction && (
                  <>
                    <AdvisorAssistant id={selected} advisorId={user?.id} />
                    <div className="detail-columns">
                      <Consultation
                        id={selected}
                        data={detail}
                        onSaved={reload}
                        canAct
                      />
                      <Handling key={selected} id={selected} data={detail} onSaved={reload} canAct />
                    </div>
                    {detail.profile?.length > 0 && <Factors data={detail} />}
                    <HistoryPanel data={detail} />
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
