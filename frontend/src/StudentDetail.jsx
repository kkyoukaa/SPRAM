import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  HelpCircle,
  History,
  ShieldAlert,
  Stethoscope,
  ClipboardList,
} from "lucide-react";
import { api, post, list, date, pct } from "./api";

const RISK_LABEL = { high: "Risiko: Tinggi", medium: "Risiko: Sedang", low: "Risiko: Rendah" };
const ANSWER_LABEL = { ya: "Ya", tidak: "Tidak", belum_tahu: "Belum tahu" };
const HELP = {
  unit: "Unit kurikuler adalah jumlah mata kuliah/unit pada dataset, bukan otomatis SKS.",
  skala: "Nilai semester memakai skala 0–20 (bukan IPK 0–4). Nilai penerimaan memakai skala 0–200.",
  peluang: "Peluang adalah perkiraan model dari pola data historis, bukan kepastian.",
};

export function Note({ children }) {
  return <p className="muted small">{children}</p>;
}
function Help({ text }) {
  return (
    <span className="help" tabIndex={0} role="note" aria-label={text} title={text}>
      <HelpCircle size={14} />
    </span>
  );
}

export function RiskSummary({ data }) {
  const p = data.prediction;
  if (!p) {
    return (
      <section className="panel padded">
        <h2>Belum ada prediksi</h2>
        <Note>Mahasiswa ini belum memiliki snapshot prediksi. Jalankan prediksi lebih dulu.</Note>
      </section>
    );
  }
  const risk = p.risk_band;
  const handling = data.case?.status || "belum";
  const handlingLabel = data.statuses?.[handling] || "Belum ditangani";
  const prob = p.probabilities || {};
  return (
    <section className="panel padded risk-summary">
      <div className="panel-title">
        <div>
          <span className="eyebrow">RINGKASAN RISIKO</span>
          <h2>{p.class_label}</h2>
          <p>
            Model memperkirakan peluang putus kuliah sebesar <strong>{pct(prob.Dropout)}</strong>.
          </p>
        </div>
        <div className="badge-stack">
          <span className={`badge ${risk}`}>{RISK_LABEL[risk] || "Risiko: —"}</span>
          <span className={`badge handling ${handling}`}>Penanganan: {handlingLabel}</span>
        </div>
      </div>
      <div className="risk-bars">
        {Object.entries(prob).map(([k, v]) => (
          <div key={k}>
            <span>{p.class_labels?.[k] || k}</span>
            <progress value={v} max="1" className={k === "Dropout" ? "high" : ""} />
            <strong>{pct(v)}</strong>
          </div>
        ))}
      </div>
      <Note>
        Perkiraan berdasarkan pola data historis, bukan kepastian. Risiko berasal dari model dan
        tidak berubah karena status penanganan. <Help text={HELP.peluang} />
      </Note>
      <div className="provenance">
        <span>Data dicatat {date(p.created_at || p.snapshot_date)}</span>
        <span>Model / {p.model_version || "—"}</span>
      </div>
    </section>
  );
}

function FactorList({ items, direction }) {
  const Icon = direction === "increase" ? ArrowUpRight : ArrowDownRight;
  if (!items.length)
    return <Note>Tidak ada faktor {direction === "increase" ? "penaik" : "penurun"} risiko yang dapat ditindaklanjuti.</Note>;
  return (
    <ul className="factor-list">
      {items.map((f) => (
        <li key={f.feature} className={direction}>
          <Icon size={16} />
          <div>
            <strong>{f.label}</strong>
            <span>{f.sentence}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Factors({ data }) {
  const f = data.factors || { increase: [], decrease: [], background: [] };
  return (
    <section className="panel padded">
      <span className="eyebrow">PENJELASAN PREDIKSI</span>
      <h2>Faktor yang paling mempengaruhi prediksi</h2>
      <p className="muted small">
        Ini faktor yang berkontribusi pada prediksi, bukan penyebab pasti. Kontribusi dihitung dari
        model yang sama dengan snapshot ini.
      </p>
      <div className="factor-columns">
        <div>
          <h3>Menaikkan risiko</h3>
          <FactorList items={f.increase} direction="increase" />
        </div>
        <div>
          <h3>Menurunkan risiko</h3>
          <FactorList items={f.decrease} direction="decrease" />
        </div>
      </div>
      {f.background?.length > 0 && (
        <div className="background-factors">
          <h3>Latar belakang</h3>
          <Note>Ditampilkan sebagai konteks, bukan dasar tindakan.</Note>
          <ul>
            {f.background.map((x) => (
              <li key={x.feature}>
                <span>{x.sentence}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function Profile({ data }) {
  const groups = {};
  (data.profile || []).forEach((row) => (groups[row.group] = groups[row.group] || []).push(row));
  return (
    <section className="panel padded">
      <span className="eyebrow">PROFIL DATA</span>
      <h2>Data mahasiswa yang dipakai model</h2>
      <p className="muted small">
        Seluruh 36 fitur dataset. Nilai bertanda • termasuk faktor teratas pada prediksi ini.
        Unit kurikuler <Help text={HELP.unit} /> · skala nilai <Help text={HELP.skala} />
      </p>
      {Object.entries(groups).map(([group, rows]) => (
        <div className="profile-group" key={group}>
          <h3>{group}</h3>
          <div className="profile-grid">
            {rows.map((row) => (
              <div className={row.highlight ? "kv highlight" : "kv"} key={row.feature}>
                <span>
                  {row.highlight && <i aria-hidden="true">•</i>} {row.label}
                </span>
                <strong>{row.value_label}</strong>
                {row.help && <small>{row.help}</small>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export function Consultation({ id, data, onSaved, canAct }) {
  const rules = data.consultation?.active_rules || [];
  const [answers, setAnswers] = useState({});
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [why, setWhy] = useState(null);
  const [saved, setSaved] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    try {
      setPreview(await post("/consultations/preview", { student_id: id, jawaban: answers }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      await post("/consultations", { student_id: id, jawaban: answers });
      setSaved("Sesi konsultasi tersimpan. Jawaban tidak mengubah prediksi model.");
      onSaved?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!rules.length)
    return (
      <section className="panel padded">
        <span className="eyebrow">KONSULTASI TERPANDU</span>
        <h2>Belum ada hipotesis</h2>
        <Note>Tidak ada aturan yang aktif untuk data mahasiswa ini.</Note>
      </section>
    );
  const answered = Object.keys(answers).length;
  return (
    <section className="panel padded consult">
      <span className="eyebrow">KONSULTASI TERPANDU</span>
      <h2>Verifikasi sinyal, lalu tentukan langkah</h2>
      <p className="muted small">
        Sistem menampilkan hipotesis dari data. Jawaban dosen memperkaya rekomendasi tindakan, tidak
        mengubah prediksi model.
      </p>
      {rules.map((r) => (
        <div className="consult-rule" key={r.rule_id}>
          <div className="consult-head">
            <span className="rule-id">{r.rule_id}</span>
            <strong>{r.nama}</strong>
          </div>
          <p>{r.hipotesis}</p>
          <p className="question">{r.pertanyaan}</p>
          <div className="choice-row" role="group" aria-label={`Jawaban ${r.rule_id}`}>
            {Object.entries(ANSWER_LABEL).map(([value, label]) => (
              <button
                key={value}
                className={answers[r.rule_id] === value ? "selected" : ""}
                onClick={() => setAnswers({ ...answers, [r.rule_id]: value })}
              >
                {label}
              </button>
            ))}
          </div>
          <details>
            <summary>Mengapa hipotesis ini muncul?</summary>
            <ul>
              {(r.alasan || []).map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </details>
        </div>
      ))}
      <div className="actions">
        <button className="primary" onClick={run} disabled={busy || !answered}>
          {busy ? "Menyusun…" : "Susun rekomendasi"}
        </button>
        <span className="muted small">
          {answered} dari {rules.length} pertanyaan dijawab
        </span>
      </div>
      {error && (
        <div className="error" role="alert">
          <AlertCircle size={16} /> {error}
        </div>
      )}
      {preview && (
        <div className="recommendations">
          <h3>Rekomendasi tindakan</h3>
          {preview.rekomendasi.map((r) => (
            <div className="recommendation" key={r.rule_id}>
              <div className="consult-head">
                <span className="rule-id">{r.rule_id}</span>
                <strong>{r.nama}</strong>
              </div>
              <ul>
                {r.tindakan.map((t) => (
                  <li key={t}>
                    <Check size={14} /> {t}
                  </li>
                ))}
              </ul>
              <button className="text-button" onClick={() => setWhy(why === r.rule_id ? null : r.rule_id)}>
                Mengapa saran ini? <ChevronRight size={14} />
              </button>
              {why === r.rule_id && (
                <div className="why">
                  <p>
                    {r.rule_id} aktif karena {(r.alasan || []).join("; ") || "kondisi aturan terpenuhi"}.
                  </p>
                  <Note>Jawaban dosen: {ANSWER_LABEL[r.jawaban] || "belum dijawab"}.</Note>
                </div>
              )}
            </div>
          ))}
          {preview.pagar_aman && (
            <div className="safeguard">
              <Stethoscope size={16} /> {preview.pagar_aman}
            </div>
          )}
          <button className="primary" onClick={save} disabled={busy || !canAct}>
            Simpan ke tindak lanjut
          </button>
          {!canAct && (
            <Note>
              Penanganan dan tindakan dilakukan oleh dosen wali. Admin hanya
              memantau status dan data mahasiswa.
            </Note>
          )}
          {saved && <p role="status">{saved}</p>}
        </div>
      )}
    </section>
  );
}

export function Handling({ id, data, onSaved, canAct }) {
  const [status, setStatus] = useState(data.case?.status || "belum");
  const [tindakan, setTindakan] = useState(data.case?.tindakan || "");
  const [catatan, setCatatan] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    setStatus(data.case?.status || "belum");
    setTindakan(data.case?.tindakan || "");
  }, [data.case?.status, data.case?.tindakan]);
  async function save(e) {
    e.preventDefault();
    setError("");
    try {
      await post("/cases", { student_id: id, status, tindakan, catatan });
      setCatatan("");
      setMessage("Status penanganan tersimpan. Nilai risiko tidak berubah.");
      onSaved?.();
    } catch (e) {
      setError(e.message);
    }
  }
  const events = data.events || [];
  return (
    <section className="panel padded">
      <span className="eyebrow">TINDAK LANJUT</span>
      <h2>Status penanganan</h2>
      <p className="muted small">
        Status penanganan adalah catatan manusia, terpisah dari risiko model. "Penanganan selesai"
        berarti langkah sudah dijalankan, bukan risiko hilang.
      </p>
      <form onSubmit={save} className="handling-form">
        <label>
          Status
          <select
            value={status}
            disabled={!canAct}
            onChange={(e) => setStatus(e.target.value)}
          >
            {Object.entries(data.statuses || {}).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tindakan
          <input
            value={tindakan}
            disabled={!canAct}
            onChange={(e) => setTindakan(e.target.value)}
            placeholder="Contoh: Rujuk ke bagian keuangan"
          />
        </label>
        {canAct && (
          <label>
            Catatan
            <textarea
              value={catatan}
              onChange={(e) => setCatatan(e.target.value)}
              placeholder="Hasil percakapan, kesepakatan, atau langkah berikutnya"
            />
          </label>
        )}
        {canAct ? (
          <button className="primary" disabled={!status}>
            <ClipboardList size={16} /> Simpan status
          </button>
        ) : (
          <Note>
            Penanganan dan tindakan dilakukan oleh dosen wali. Admin hanya
            memantau status dan data mahasiswa.
          </Note>
        )}
        {message && <p role="status">{message}</p>}
        {error && <p className="error">{error}</p>}
      </form>
      <h3>Riwayat penanganan</h3>
      {events.length ? (
        <ol className="timeline">
          {events.map((e) => (
            <li key={e.event_id}>
              <span className="dot" aria-hidden="true" />
              <div>
                <strong>
                  {data.statuses?.[e.status_baru] || e.status_baru}
                  {e.status_lama ? ` (dari ${data.statuses?.[e.status_lama] || e.status_lama})` : ""}
                </strong>
                <small>{date(e.timestamp)}</small>
                {e.catatan && <p>{e.catatan}</p>}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <Note>Belum ada riwayat perubahan status.</Note>
      )}
    </section>
  );
}

export function HistoryPanel({ data }) {
  const rows = data.history || [];
  return (
    <section className="panel padded">
      <span className="eyebrow">RIWAYAT</span>
      <h2>Riwayat prediksi</h2>
      <p className="muted small">Setiap snapshot disimpan terpisah dan tidak menimpa yang lama.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Tanggal pencatatan</th>
              <th>Hasil</th>
              <th>Peluang putus kuliah</th>
              <th>Risiko</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{date(r.created_at || r.snapshot_date)}</td>
                <td>{r.class_label}</td>
                <td className="number">{pct(r.probabilities?.Dropout)}</td>
                <td>
                  <span className={`badge ${r.risk_band}`}>{RISK_LABEL[r.risk_band]?.replace("Risiko: ", "") || "—"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <Note>Belum ada snapshot untuk ID ini.</Note>}
      </div>
    </section>
  );
}

function EditStudent({ id, data, onSaved }) {
  const s = data.student || {};
  const [form, setForm] = useState({
    cohort: s.cohort || "",
    program_code: s.program_code === "—" ? "" : s.program_code || "",
    active_status: s.active_status || "active",
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    setForm({
      cohort: s.cohort || "",
      program_code: s.program_code === "—" ? "" : s.program_code || "",
      active_status: s.active_status || "active",
    });
  }, [s.cohort, s.program_code, s.active_status]);
  async function save(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api(`/students/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
      setMessage("Data mahasiswa tersimpan.");
      onSaved?.();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <section className="panel padded">
      <span className="eyebrow">DATA MAHASISWA</span>
      <h2>Edit data induk</h2>
      <p className="muted small">
        Admin mengelola data induk mahasiswa. Penanganan dan tindakan tetap
        dilakukan oleh dosen wali.
      </p>
      <form onSubmit={save} className="handling-form">
        <label>
          Angkatan
          <input
            value={form.cohort}
            onChange={(e) => setForm({ ...form, cohort: e.target.value })}
            placeholder="Contoh: 2026"
          />
        </label>
        <label>
          Program studi (kode)
          <input
            value={form.program_code}
            onChange={(e) => setForm({ ...form, program_code: e.target.value })}
            placeholder="Contoh: TI"
          />
        </label>
        <label>
          Status akademik
          <select
            value={form.active_status}
            onChange={(e) => setForm({ ...form, active_status: e.target.value })}
          >
            <option value="active">Aktif</option>
            <option value="cuti">Cuti</option>
            <option value="lulus">Lulus</option>
            <option value="dropout">Putus kuliah</option>
          </select>
        </label>
        <button className="primary">
          <ClipboardList size={16} /> Simpan data
        </button>
        {message && <p role="status">{message}</p>}
        {error && <p className="error">{error}</p>}
      </form>
    </section>
  );
}

const ASSIST_INTENTS = [
  { id: "why", label: "Mengapa berisiko?" },
  { id: "intervention", label: "Apa saran tindakannya?" },
  { id: "changes", label: "Apa yang berubah?" },
  { id: "confidence", label: "Seberapa yakin model?" },
  { id: "profile", label: "Data apa yang dipakai?" },
];

export function AdvisorAssistant({ id, advisorId }) {
  const sesiKey = `spram-chat-sesi-${advisorId || "x"}-${id}`;
  const [reco, setReco] = useState(null);
  const [recoError, setRecoError] = useState("");
  const [sessions, setSessions] = useState([]);
  const [aktif, setAktif] = useState(null);
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [siap, setSiap] = useState(false);

  // muat daftar sesi milik dosen ini, lalu pilih yang terakhir atau buat baru
  useEffect(() => {
    let alive = true;
    setSiap(false);
    setMessages([]);
    setReco(null);
    api("/chat/sessions")
      .then((d) => {
        if (!alive) return;
        const daftar = list(d, "items").filter((s) => s.student_id === id);
        setSessions(daftar);
        if (daftar.length) bukaSesi(daftar[0].id);
        else sesiBaru();
        setSiap(true);
      })
      .catch((e) => {
        if (!alive) return;
        // jangan telan diam-diam: kalau riwayat gagal dimuat, dosen harus tahu
        setRecoError(`Riwayat percakapan gagal dimuat: ${e.message}`);
        setSiap(true);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, advisorId]);

  useEffect(() => {
    let alive = true;
    setRecoError("");
    api(`/students/${encodeURIComponent(id)}/recommendations`)
      .then((d) => alive && setReco(d))
      .catch((e) => alive && setRecoError(e.message));
    return () => {
      alive = false;
    };
  }, [id]);

  async function bukaSesi(sid) {
    try {
      const d = await api(`/chat/sessions/${sid}/messages`);
      setAktif(sid);
      setMessages(
        list(d, "items").map((m) => ({ role: m.role, text: m.content })),
      );
      try {
        localStorage.setItem(sesiKey, sid);
      } catch {
        /* mode privat */
      }
    } catch (e) {
      setRecoError(e.message);
    }
  }

  function sesiBaru() {
    setAktif(null);
    setMessages([]);
    try {
      localStorage.removeItem(sesiKey);
    } catch {
      /* mode privat */
    }
  }

  async function hapusSesi(sid) {
    if (!confirm("Hapus percakapan ini?")) return;
    try {
      await api(`/chat/sessions/${sid}`, { method: "DELETE" });
      const sisa = sessions.filter((s) => s.id !== sid);
      setSessions(sisa);
      if (aktif === sid) {
        if (sisa.length) bukaSesi(sisa[0].id);
        else sesiBaru();
      }
    } catch (e) {
      setRecoError(e.message);
    }
  }

  async function ask(payload, label) {
    const history = messages.map((m) => ({ role: m.role, content: m.text }));
    setMessages((m) => [...m, { role: "user", text: label }]);
    setBusy(true);
    let sid = aktif;
    try {
      if (!sid) {
        const s = await api("/chat/sessions", {
          method: "POST",
          body: JSON.stringify({ student_id: id }),
        });
        sid = s.id;
        setAktif(sid);
        setSessions((l) => [
          { id: sid, student_id: id, title: "Percakapan baru" },
          ...l,
        ]);
      }
      const d = await post(
        `/students/${encodeURIComponent(id)}/assistant`,
        { ...payload, history, session_id: sid },
      );
      setMessages((m) => [
        ...m,
        { role: "assistant", text: d.answer, mode: d.mode },
      ]);
      if (d.session) {
        setSessions((l) =>
          l.map((s) => (s.id === d.session.id ? { ...s, ...d.session } : s)),
        );
      }
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `Maaf, pesan gagal terkirim: ${e.message}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function freeText(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    ask({ question: text }, text);
  }
  const rekomendasi = reco?.rekomendasi || [];
  return (
    <section className="panel padded chat-panel">
      <div className="chat-head">
        <div>
          <h2>Percakapan</h2>
          <p className="muted small">
            Tanyakan apa saja soal mahasiswa ini. Jawaban berpijak pada data dan
            catatan penanganan.
          </p>
        </div>
        <button type="button" className="text-button" onClick={sesiBaru}>
          Percakapan baru
        </button>
      </div>

      {sessions.length > 0 && (
        <div className="chat-sessions" aria-label="Riwayat percakapan">
          {sessions.map((s) => (
            <span
              key={s.id}
              className={`chat-session ${s.id === aktif ? "active" : ""}`}
            >
              <button type="button" onClick={() => bukaSesi(s.id)}>
                {s.title || "Percakapan"}
              </button>
              <button
                type="button"
                className="chat-session-del"
                aria-label={`Hapus ${s.title || "percakapan"}`}
                onClick={() => hapusSesi(s.id)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="chat-thread" aria-live="polite">
        {!messages.length && (
          <div className="chat-bubble assistant">
            <p>
              Halo, saya bisa bantu membaca hasil analisis mahasiswa ini. Mau
              mulai dari mana?
            </p>
          </div>
        )}
        {messages.map((m, index) => (
          <div key={index} className={`chat-bubble ${m.role}`}>
            <p>{m.text}</p>
            {m.mode === "terbatas" && (
              <small>Sesi terbatas — balasan disusun dari data yang ada.</small>
            )}
          </div>
        ))}
        {busy && (
          <div className="chat-bubble assistant typing">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      <div className="choice-row" role="group" aria-label="Pertanyaan cepat">
        {ASSIST_INTENTS.map((i) => (
          <button
            key={i.id}
            type="button"
            className="chip"
            disabled={busy || !siap}
            onClick={() => ask({ intent: i.id }, i.label)}
          >
            {i.label}
          </button>
        ))}
      </div>

      <form onSubmit={freeText} className="chat-compose">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Tulis pesan…"
          aria-label="Tulis pesan"
          disabled={busy}
        />
        <button className="primary" disabled={busy || !input.trim()}>
          Kirim
        </button>
      </form>
      <p className="chat-footnote">
        Hasil analisis bersifat perkiraan, bukan keputusan otomatis. Verifikasi
        bersama mahasiswa sebelum bertindak.
      </p>

      <details className="chat-reco">
        <summary>Lihat saran tindakan ({rekomendasi.length})</summary>
        {recoError && <p className="error">{recoError}</p>}
        {reco && !rekomendasi.length && (
          <Note>Tidak ada aturan yang aktif untuk data mahasiswa ini.</Note>
        )}
        {rekomendasi.length > 0 && (
          <div className="recommendations">
            {rekomendasi.map((r) => (
              <div className="recommendation" key={r.rule_id}>
                <div className="consult-head">
                  <strong>{r.nama}</strong>
                </div>
                <p className="muted small">{r.hipotesis}</p>
                <p className="small">
                  <strong>Dasar data:</strong>{" "}
                  {(r.alasan || []).join("; ") || "Sinyal data perlu ditinjau"}
                </p>
                <p className="small">
                  <strong>Tanyakan:</strong> {r.verifikasi}
                </p>
                <ul>
                  {(r.sementara || []).map((t) => (
                    <li key={t}>
                      <Check size={14} /> {t}
                    </li>
                  ))}
                </ul>
                <p className="muted small">
                  Jika terkonfirmasi:{" "}
                  {(r.jika_ya || []).join("; ") || "diskusikan langkah lanjutan"}.
                  Jika tidak:{" "}
                  {(r.jika_tidak || []).join("; ") || "periksa sinyal lain"}.
                </p>
              </div>
            ))}
          </div>
        )}
        {reco?.pagar_aman && (
          <div className="safeguard">
            <Stethoscope size={16} /> {reco.pagar_aman}
          </div>
        )}
      </details>
    </section>
  );
}

export default function StudentDetail({ id, user, onClose, onOpenHandling }) {
  const canAct = user?.role === "advisor";
  const isAdmin = user?.role === "admin";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setError("");
    setData(null);
    api(`/students/${encodeURIComponent(id)}/detail`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [id, tick]);
  const reload = () => setTick((t) => t + 1);
  return (
    <>
      <button className="text-button" onClick={onClose}>
        Mahasiswa / Kembali
      </button>
      <div className="page-heading">
        <div>
          <span className="eyebrow">DETAIL MAHASISWA</span>
          <h1>{id}</h1>
          <p>
            {data?.student?.program_code && data.student.program_code !== "—"
              ? `Program ${data.student.program_code} · `
              : ""}
            Risiko, faktor, profil, konsultasi, dan tindak lanjut dalam satu halaman.
          </p>
        </div>
        {data?.case && (
          <span className={`badge handling ${data.case.status}`}>
            <ShieldAlert size={14} /> {data.case.status_label}
          </span>
        )}
      </div>
      {error && (
        <div className="error" role="alert">
          <AlertCircle size={18} /> {error}
        </div>
      )}
      {!data && !error && <div className="panel padded">Memuat detail…</div>}
      {data && (
        <>
          <RiskSummary data={data} />
          {data.prediction && <Factors data={data} />}
          {data.profile?.length > 0 && <Profile data={data} />}
          {isAdmin && (
            <EditStudent id={id} data={data} onSaved={reload} />
          )}
          {canAct && (
            <section className="panel padded">
              <span className="eyebrow">PENANGANAN</span>
              <h2>Lanjutkan di menu Penanganan</h2>
              <p className="muted small">
                Rekomendasi tindakan, chatbot pendamping, konsultasi terpandu,
                dan status penanganan dikelola di menu Penanganan.
              </p>
              <button
                className="primary"
                onClick={() => onOpenHandling?.(id)}
              >
                <ClipboardList size={16} /> Buka penanganan
              </button>
            </section>
          )}
          <HistoryPanel data={data} />
        </>
      )}
    </>
  );
}
