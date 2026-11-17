import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  Users,
  FlaskConical,
  Upload,
  Activity,
  ShieldCheck,
  LogOut,
  Menu,
  ArrowUpRight,
  GraduationCap,
  ChevronRight,
  X,
  AlertCircle,
  BookOpen,
  ClipboardList,
  Cpu,
} from "lucide-react";
import { api, post, list, pct, date } from "./api";
import "./style.css";
import ModelEvaluation from "./ModelEvaluation";
import StudentDirectory from "./StudentDirectory";
import StudentDetail from "./StudentDetail";
import RulesAdmin from "./RulesAdmin";
import Penanganan from "./Penanganan";
import LlmSettings from "./LlmSettings";

import CohortTrend from "./CohortTrend";
import ChatWidget from "./ChatWidget";
import { probabilityPercentages } from "./format";

const navigation = [
  ["dashboard", "Ringkasan", LayoutDashboard],
  ["students", "Mahasiswa", Users],
  ["handling", "Penanganan", ClipboardList],
  ["predict", "Prediksi", Activity],
  ["rules", "Aturan", BookOpen],
  ["batch", "Dataset", Upload],
  ["models", "Model Center", FlaskConical],
  ["llm", "Pengaturan model", Cpu],
  ["users", "Pengguna & audit", ShieldCheck],
];
const ADMIN_PAGES = ["predict", "rules", "batch", "models", "llm", "users"];
const stageName = (s) => (s === "intake" ? "Intake" : "Academic Update");
function Badge({ value }) {
  return (
    <span className={`badge ${value || ""}`}>
      {{
        high: "Risiko tinggi",
        medium: "Risiko sedang",
        low: "Risiko rendah",
        candidate: "Kandidat",
        champion: "Champion",
        experimental: "Experimental",
        completed: "Selesai",
        running: "Berjalan",
        queued: "Antrean",
        failed: "Gagal",
        partial: "Sebagian",
        admin: "Admin",
        advisor: "Dosen wali",
      }[value] ||
        value ||
        "Belum diprediksi"}
    </span>
  );
}
function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{Number(value || 0).toLocaleString("id-ID")}</strong></div>;
}
function Empty({ children = "Belum ada data tersedia." }) {
  return (
    <div className="empty">
      <Activity size={26} />
      <p>{children}</p>
    </div>
  );
}
function ErrorBox({ error }) {
  return error ? (
    <div className="error" role="alert">
      <AlertCircle size={18} />
      {String(error)}
    </div>
  ) : null;
}
function Stage({ value, onChange }) {
  return (
    <div className="segmented">
      <button
        className={value === "intake" ? "selected" : ""}
        onClick={() => onChange("intake")}
      >
        Intake
      </button>
      <button
        className={value === "academic_update" ? "selected" : ""}
        onClick={() => onChange("academic_update")}
      >
        Academic Update
      </button>
    </div>
  );
}
function useLoad(path, tick = 0) {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api(path)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [path, tick]);
  return { data, error, loading };
}
function Login({ onLogin }) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await post("/auth/login", { email, password });
      onLogin(d.user || d);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login">
      <section className="login-story">
        <div className="brand">
          <GraduationCap size={30} />
          <span>
            SPRAM<span className="brand-sub">ACADEMIC SUPPORT SYSTEM</span>
          </span>
        </div>
        <div>
          <span className="eyebrow light">DATA UNTUK PENDAMPINGAN</span>
          <h1>
            Kenali risikonya.
            <br />
            Dampingi
            <br />
            <em>perjalanannya.</em>
          </h1>
          <p>
            Informasi akademik yang dapat dijelaskan, untuk langkah pendampingan
            yang lebih terarah.
          </p>
          <div className="login-stages">
            <span>01 / Intake</span>
            <span>02 / Academic Update</span>
          </div>
        </div>
        <small>
          Prototipe akademik · Dataset UCI · Bukan keputusan otomatis
        </small>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <span className="eyebrow">RUANG KERJA AKADEMIK</span>
          <h2>Selamat datang.</h2>
          <p className="muted">Masuk sebagai Admin atau Dosen Wali.</p>
          <ErrorBox error={error} />
          <label>
            Email
            <input
              autoComplete="username"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nama@kampus.ac.id"
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Masukkan password"
            />
          </label>
          <button className="primary full" disabled={busy}>
            {busy ? "Memverifikasi…" : "Masuk"}
          </button>
          <p className="login-note">
            Akses mahasiswa dibatasi sesuai penugasan dosen.
          </p>
        </form>
        <small>SPRAM / Sistem Prediksi Risiko Akademik Mahasiswa</small>
      </section>
    </div>
  );
}
function StudentTable({ rows, onStudent }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Mahasiswa</th>
            <th>Program studi</th>
            <th>Peluang putus kuliah</th>
            <th>Risiko</th>
            <th>Penanganan</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((raw, i) => {
            const s = { ...raw, ...(raw.latest_prediction || {}) };
            return (
              <tr key={s.student_id || i}>
                <td>
                  <button
                    className="text-button"
                    onClick={() => onStudent(s.student_id)}
                  >
                    {s.student_id}
                  </button>
                  <small>{s.info?.program || "Program belum tersedia"}</small>
                </td>
                <td>
                  {s.info?.program || "—"}
                  <small>
                    Usia {s.info?.age || "—"} · {s.info?.gender || "—"}
                  </small>
                </td>
                <td className="number">
                  {s.probabilities ? pct(s.probabilities.Dropout) : "—"}
                </td>
                <td>
                  <Badge value={s.risk_band} />
                </td>
                <td>
                  <span className={`badge handling ${s.case?.status || "belum"}`}>
                    {s.case?.status_label || "Belum ditangani"}
                  </span>
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={`Detail ${s.student_id}`}
                    onClick={() => onStudent(s.student_id)}
                  >
                    <ChevronRight size={18} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length && <Empty />}
    </div>
  );
}
function Dashboard({ onNavigate, onStudent }) {
  const { data, error, loading } = useLoad("/dashboard/summary");
  const risks = data?.risk_distribution || data?.risk_counts || {};
  const rows = data?.high_risk_untreated || data?.priority_students || [];
  const monitored = data?.high_risk_monitored || [];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">GAMBARAN COHORT</span>
          <h1>Ringkasan mahasiswa</h1>
          <p>Gambaran singkat data mahasiswa dan hasil prediksi terbaru.</p>
        </div>
        <button className="primary" onClick={() => onNavigate("predict")}>
          Prediksi baru <ArrowUpRight size={17} />
        </button>
      </div>
      <ErrorBox error={error} />
      <div className="stats">
        <div>
          <span>Total mahasiswa</span>
          <strong>{loading ? "…" : (data?.total_students ?? "—")}</strong>
          <small>Dalam lingkup akses Anda</small>
        </div>
        <div>
          <span>Prediksi putus kuliah</span>
          <strong className="red">
            {loading ? "…" : (data?.class_distribution?.Dropout ?? 0)}
          </strong>
          <small>Hasil kelas terbesar pada snapshot terbaru</small>
        </div>
        <div>
          <span>Prediksi masih aktif</span>
          <strong>{loading ? "…" : (data?.class_distribution?.Enrolled ?? 0)}</strong>
          <small>Mahasiswa diprediksi tetap terdaftar</small>
        </div>
        <div>
          <span>Prediksi lulus</span>
          <strong>{loading ? "…" : (data?.class_distribution?.Graduate ?? 0)}</strong>
          <small>Mahasiswa diprediksi menyelesaikan studi</small>
        </div>
        <div>
          <span>Belum ditangani</span>
          <strong className="red">{loading ? "…" : (data?.untreated_count ?? 0)}</strong>
          <small>Risiko tinggi tanpa catatan penanganan</small>
        </div>
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-title">
            <div>
              <h2>Risiko tinggi, belum ditangani</h2>
              <p>Prioritas utama, diurutkan dari peluang putus kuliah tertinggi.</p>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("students")}
            >
              Lihat semua <ChevronRight size={15} />
            </button>
          </div>
          <StudentTable rows={rows} onStudent={onStudent} />
        </section>
        <section className="panel distribution">
          <span className="eyebrow">DISTRIBUSI RISIKO</span>
          <h2>Mulai dari yang perlu perhatian.</h2>
          {["high", "medium", "low"].map((r) => (
            <div className="risk-row" key={r}>
              <div>
                <Badge value={r} />
                <strong>{risks[r] || 0}</strong>
              </div>
              <progress
                className={r}
                value={risks[r] || 0}
                max={Math.max(
                  1,
                  Object.values(risks).reduce((a, b) => a + Number(b || 0), 0),
                )}
              />
            </div>
          ))}
          <p className="muted small">
            Risiko ditentukan dari peluang putus kuliah, bukan label kelas terbesar.
            Status penanganan tidak mengubah nilai risiko.
          </p>
        </section>
      </div>
      <section className="panel">
        <div className="panel-title">
          <div>
            <h2>Risiko tinggi, sedang dipantau</h2>
            <p>Sudah ditangani tetapi tetap berisiko tinggi. Tidak pernah hilang dari daftar.</p>
          </div>
          <span className="counter">{monitored.length} mahasiswa</span>
        </div>
        <StudentTable rows={monitored} onStudent={onStudent} />
      </section>
      <div className="disclaimer">
        <ShieldCheck size={21} />
        <p>
          <strong>Alat bantu, bukan penentu.</strong> Prediksi mendukung
          prioritisasi pendampingan. Validasi konteks bersama mahasiswa sebelum
          mengambil tindakan.
        </p>
        <span>PROTOTIPE AKADEMIK</span>
      </div>

    </>
  );
}

function Result({ result }) {
  if (!result) return null;
  const p = result.probabilities || {};
  const display = probabilityPercentages(p);
  const KELAS = { Dropout: "Putus kuliah", Enrolled: "Masih aktif", Graduate: "Lulus" };
  const predicted = KELAS[result.predicted_class] || result.class_label || result.predicted_class || "Prediksi";
  const meaning = {
    "Putus kuliah": "Mahasiswa terindikasi berisiko tidak melanjutkan studi dan perlu ditinjau lebih lanjut.",
    "Masih aktif": "Mahasiswa diprediksi tetap terdaftar dan melanjutkan studi.",
    Lulus: "Mahasiswa diprediksi menyelesaikan studi.",
  }[predicted];
  const explanation = result.explanation || result;
  const drivers = explanation.top_drivers || [],
    protectors = explanation.top_protectors || [];
  return (
    <section className="panel result" aria-live="polite">
      <div className="panel-title">
        <div>
          <span className="eyebrow">HASIL PREDIKSI</span>
          <h2>{predicted}</h2>
          {meaning && <p>{meaning}</p>}
        </div>
        <Badge value={result.risk_band} />
      </div>
      <h3>Probabilitas setiap kelas</h3>
      <div className="probabilities">
        {["Dropout", "Enrolled", "Graduate"].map((k) => (
          <div key={k}>
            <span>{KELAS[k]}</span>
            <strong>{display[k]}</strong>
            <progress value={p[k] || 0} max="1" />
          </div>
        ))}
      </div>
      <div className="driver-grid">
        <div>
          <h3>Faktor pendorong</h3>
          {drivers.map((d, i) => (
            <div className="driver" key={i}>
              <span>{d.label || d.feature}</span>
              <strong className="red">
                +{Number(d.shap ?? d.value ?? 0).toFixed(3)}
              </strong>
            </div>
          ))}
          {!drivers.length && (
            <p className="muted">
              Tidak ada faktor positif, atau penjelasan belum tersedia.
            </p>
          )}
        </div>
        <div>
          <h3>Faktor pelindung</h3>
          {protectors.map((d, i) => (
            <div className="driver" key={i}>
              <span>{d.label || d.feature}</span>
              <strong className="green">
                {Number(d.shap ?? d.value ?? 0).toFixed(3)}
              </strong>
            </div>
          ))}
          {!protectors.length && (
            <p className="muted">
              Tidak ada faktor negatif, atau penjelasan belum tersedia.
            </p>
          )}
        </div>
      </div>
      <p className="small muted">
        Faktor di atas menjelaskan kontribusi terhadap skor model, bukan hubungan
        sebab-akibat. {explanation.output_space || ""}
      </p>
      <div className="provenance">
        <span>Model / {result.model_version || "—"}</span>
        <span>{date(result.created_at || result.timestamp)}</span>
      </div>
    </section>
  );
}
function Predict({ user }) {
  const [mode, setMode] = useState("manual"),
    [stage] = useState("academic_update"),
    [values, setValues] = useState({}),
    [student, setStudent] = useState(""),
    [snapshot, setSnapshot] = useState(
      new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Jakarta" }),
    ),
    [result, setResult] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [step, setStep] = useState(0),
    [showChat, setShowChat] = useState(false);
  const { data: activeData } = useLoad("/admin/models/active");
  const activeStages = Object.keys(activeData?.active || {});
  const { data: schema, error: schemaError } = useLoad(
    `/model-schemas/${stage}/active`,
  );
  const fields = Array.isArray(schema?.features)
    ? schema.features
    : Array.isArray(schema?.fields)
      ? schema.fields
      : [];
  const groups = [
    "Penerimaan & demografi",
    "Biaya & ekonomi",
    "Performa akademik",
    "Konteks makro",
  ]
    .map((name) => [name, fields.filter((f) => f.group === name)])
    .filter((g) => g[1].length);
  useEffect(() => {
    setValues({});
    setStep(0);
    setResult(null);
  }, [stage]);
  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const features = Object.fromEntries(
        Object.entries(values).map(([k, v]) => [k, Number(v)]),
      );
      const d = await post("/predictions", {
        student_id: student,
        snapshot_date: snapshot,
        stage,
        prediction_stage: stage,
        features,
        schema_version: schema?.schema_version,
        idempotency_key:
          globalThis.crypto?.randomUUID?.() ||
          `prediction-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      });
      setResult(d.prediction || d);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PREDIKSI</span>
          <h1>Dari data ke langkah nyata.</h1>
          <p>Prediksi Academic Update menggunakan Main Model yang sudah tersedia.</p>
        </div>
      </div>
      <div className="segmented">
        <button className={mode === "manual" ? "selected" : ""} onClick={() => setMode("manual")}>Prediksi Manual</button>
        <button className={mode === "batch" ? "selected" : ""} onClick={() => setMode("batch")}>Prediksi PDF / XLSX / CSV</button>
      </div>
      {!activeStages.includes("academic_update") && <ErrorBox error="Main Model Academic Update belum tersedia." />}
      {mode === "batch" ? <BatchPrediction stage={stage} /> : <>
      <ErrorBox error={schemaError || error} />
      <div className="prediction-layout">
        <form className="panel form-panel" onSubmit={submit}>
          <div className="panel-title">
            <div>
              <h2>Prediksi satu mahasiswa</h2>
              <p>Field otomatis mengikuti fitur Main Model Academic Update yang aktif. Prediksi memakai model tersebut tanpa training ulang.</p>
            </div>
            <span className="counter">{fields.length} fitur</span>
          </div>
          <div className="form-grid">
            <label>
              ID mahasiswa
              <input
                required
                value={student}
                onChange={(e) => setStudent(e.target.value)}
                placeholder="STD-0001"
              />
            </label>
            <label>
              Tanggal snapshot
              <input
                required
                type="date"
                value={snapshot}
                onChange={(e) => setSnapshot(e.target.value)}
              />
            </label>
          </div>
          <div className="form-tabs">
            {groups.map(([name], i) => (
              <button
                key={name}
                type="button"
                className={step === i ? "active" : ""}
                onClick={() => setStep(i)}
              >
                {i + 1}. {name}
              </button>
            ))}
          </div>
          {groups.map(([name, items], i) => (
            <fieldset
              key={name}
              style={{ display: step === i ? "block" : "none" }}
            >
              <legend>{name}</legend>
              <div className="form-grid">
                {items.map((raw) => {
                  const f = typeof raw === "string" ? { name: raw } : raw;
                  const categories = f.categories || f.enum || f.allowed_values;
                  return (
                    <label key={f.name}>
                      {f.label || f.name}
                      {categories ? (
                        <select
                          required
                          value={values[f.name] ?? ""}
                          onChange={(e) =>
                            setValues({ ...values, [f.name]: e.target.value })
                          }
                        >
                          <option value="">Pilih…</option>
                          {(Array.isArray(categories)
                            ? categories
                            : Object.entries(categories).map(
                                ([value, label]) => ({ value, label }),
                              )
                          ).map((c) => (
                            <option key={c.value ?? c} value={c.value ?? c}>
                              {c.label ?? c}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          step={f.type === "integer" ? "1" : "any"}
                          min={f.min ?? f.minimum}
                          max={f.max ?? f.maximum}
                          required
                          value={values[f.name] ?? ""}
                          onChange={(e) =>
                            setValues({ ...values, [f.name]: e.target.value })
                          }
                        />
                      )}
                      <small className="muted">
                        {f.help || (!categories && `Rentang ${f.min ?? f.minimum}–${f.max ?? f.maximum}`)}
                      </small>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}
          {!fields.length && (
            <Empty>
              Schema model aktif belum tersedia. Admin perlu melatih dan
              mempromosikan model.
            </Empty>
          )}
          <div className="form-footer">
            <span className="muted small">
              {Object.keys(values).filter((k) => values[k] !== "").length} /{" "}
              {fields.length} fitur terisi
            </span>
            {step < groups.length - 1 ? (
              <button
                type="button"
                className="primary"
                onClick={() => setStep(step + 1)}
              >
                Lanjut <ChevronRight size={16} />
              </button>
            ) : (
              <button
                className="primary"
                disabled={
                  busy ||
                  !activeStages.includes("academic_update") ||
                  !fields.length ||
                  fields.some(
                    (f) =>
                      values[f.name || f] == null || values[f.name || f] === "",
                  )
                }
              >
                {busy ? "Menghitung…" : "Jalankan prediksi"}
                <Activity size={16} />
              </button>
            )}
          </div>
        </form>
        <aside className="context-panel">
          <span className="eyebrow">SEBELUM MEMULAI</span>
          <h2>
            Data tepat.
            <br />
            Interpretasi bijak.
          </h2>
          <p>
            Nilai penerimaan memakai skala 0–200. Nilai semester memakai skala
            0–20, bukan IPK 0–4.
          </p>
          <hr />
          <p>
            Unit kurikuler adalah jumlah mata kuliah atau unit pada dataset,
            bukan otomatis SKS.
          </p>
          <hr />
          <p>
            Data berasal dari Portugal. Hasil belum membuktikan validitas untuk
            mahasiswa Indonesia.
          </p>
        </aside>
      </div>
      <Result result={result} />
      {result && user?.role === "advisor" && !showChat && (
        <button className="chat-fab" onClick={() => setShowChat(true)} aria-label="Buka asisten" style={{position:'fixed',bottom:24,right:24,width:56,height:56,borderRadius:'50%',background:'#0B1F3A',color:'#fff',border:'none',fontSize:24,cursor:'pointer',boxShadow:'0 4px 12px rgba(11,31,58,.3)',zIndex:999}}>🤖</button>
      )}
      {result && user?.role === "advisor" && showChat && (
        <ChatWidget predictionId={result.id} onClose={() => setShowChat(false)} />
      )}
      </>}
    </>
  );
}
function BatchPrediction({ stage }) {
  const [file,setFile]=useState(null),[job,setJob]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  useEffect(()=>{if(!job?.id||!["queued","running"].includes(job.status))return;const timer=setInterval(()=>api(`/batch-jobs/${job.id}`).then(setJob).catch(e=>setError(e.message)),1500);return()=>clearInterval(timer)},[job?.id,job?.status]);
  async function upload(e){e.preventDefault();setBusy(true);setError("");try{const form=new FormData();form.append("stage",stage);form.append("file",file);const created=await api("/batch-jobs",{method:"POST",body:form});if(created.status!=="validated")return setJob(created);const queued=await post(`/batch-jobs/${created.id}/run`);setJob({...created,...queued})}catch(e){setError(e.message)}finally{setBusy(false)}}
  const preview=job?.preview||[],results=job?.results||[];
  return <><ErrorBox error={error}/><form className="panel upload-panel" onSubmit={upload}><Upload size={35}/><h2>Prediksi sekaligus dari Excel / CSV</h2><p>Setiap baris dianggap satu mahasiswa. ID yang sudah pernah diprediksi atau berulang dalam file akan dilewati.</p><a href={`/api/templates/${stage}.csv`}>Unduh Template CSV</a><input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required onChange={e=>{setFile(e.target.files[0]);setJob(null)}}/><button className="primary" disabled={busy||!file}>{busy?"Memproses…":"Upload & Jalankan Prediksi"}</button></form>{job&&<section className="panel padded" aria-live="polite"><div className="panel-title"><div><h2>{results.length?"Hasil Prediksi":"Preview & Validasi"}</h2><p><Badge value={job.status}/> · Siap: <strong>{job.valid_count??0}</strong> · Dilewati: <strong>{job.skipped_count??0}</strong> · Invalid: <strong>{job.invalid_count??0}</strong></p></div>{["completed","partial"].includes(job.status)&&<a className="primary" href={`/api/batch-jobs/${job.id}/export`}>Download Hasil CSV</a>}</div>{!results.length&&["queued","running"].includes(job.status)&&<p className="muted">Prediksi sedang diproses…</p>}{results.length>0&&<div className="table-wrap"><table><thead><tr><th>ID Mahasiswa</th><th>Prediction</th><th>Status</th><th>Dropout</th><th>Enrolled</th><th>Graduate</th></tr></thead><tbody>{results.map(x=><tr key={x.id}><td>{x.student_id}</td><td><strong>{x.predicted_class}</strong></td><td><Badge value={x.status==="success"?"completed":x.status}/></td><td>{pct(x.probabilities?.Dropout)}</td><td>{pct(x.probabilities?.Enrolled)}</td><td>{pct(x.probabilities?.Graduate)}</td></tr>)}</tbody></table></div>}{job.errors?.length>0&&<div className="error">{job.errors.slice(0,50).map(x=><div key={x.row}>Baris {x.row}: {x.message}</div>)}</div>}</section>}</>;
}
function Batch() {
  const [file,setFile]=useState(null),[datasets,setDatasets]=useState([]),[selected,setSelected]=useState(null),[report,setReport]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[checking,setChecking]=useState("");
  const load=()=>api("/datasets").then(d=>setDatasets(list(d,"items"))).catch(e=>setError(e.message));
  useEffect(()=>{load();},[]);
  async function upload(e){e.preventDefault();setBusy(true);setError("");try{const form=new FormData();form.append("file",file);await api("/datasets",{method:"POST",body:form});setFile(null);load();}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function view(d){try{setSelected(await api(`/datasets/${d.id}`));}catch(e){setError(e.message)}}
  async function preprocess(d){setChecking(d.id);setError("");setReport(null);try{const r=await post(`/datasets/${d.id}/preprocess`);setReport({...r.preprocessing,name:d.name,status:r.status});await load();requestAnimationFrame(()=>document.getElementById("preprocessing-result")?.scrollIntoView({behavior:"smooth",block:"start"}));}catch(e){setError(e.message)}finally{setChecking("")}}
  async function edit(d){const name=prompt("Nama dataset",d.name);if(!name?.trim())return;try{await api(`/datasets/${d.id}`,{method:"PATCH",body:JSON.stringify({name:name.trim()})});load();}catch(e){setError(e.message)}}
  async function remove(d){if(!confirm(`Delete dataset ${d.name}?`))return;try{await api(`/datasets/${d.id}`,{method:"DELETE"});load();}catch(e){setError(e.message)}}
  return <>
    <div className="page-heading"><div><span className="eyebrow">DATASET</span><h1>Dataset</h1><p>Upload, periksa kualitas, lihat isi, edit metadata, dan hapus dataset.</p></div></div>
    <ErrorBox error={error}/>
    <form className="panel upload-panel" onSubmit={upload}><Upload size={35}/><h2>Unggah dataset</h2><p>CSV UTF-8 · delimiter titik koma · maksimal 20 MB</p><input type="file" accept=".csv,text/csv" required onChange={e=>setFile(e.target.files[0])}/><button className="primary" disabled={busy||!file}>{busy?"Mengunggah…":"Unggah dataset"}</button></form>
    <section className="panel"><div className="panel-title"><div><h2>Dataset tersimpan</h2><p>Training hanya tersedia di Model Center setelah preprocessing lulus.</p></div></div><div className="table-wrap"><table><thead><tr><th>Nama</th><th>Baris</th><th>Kolom</th><th>Status</th><th>Diunggah</th><th>Aksi</th></tr></thead><tbody>{datasets.map(d=><tr key={d.id}><td>{d.name}</td><td>{d.row_count?.toLocaleString()}</td><td>{d.col_count}</td><td><Badge value={d.status}/></td><td>{date(d.created_at)}</td><td><div className="actions"><button onClick={()=>view(d)}>View</button><button disabled={Boolean(checking)} onClick={()=>preprocess(d)}>{checking===d.id?"Memeriksa…":"Preprocessing"}</button><button onClick={()=>edit(d)}>Edit</button><button className="danger" onClick={()=>remove(d)}>Delete</button></div></td></tr>)}</tbody></table>{!datasets.length&&<Empty>Belum ada dataset.</Empty>}</div></section>
    {report&&<section id="preprocessing-result" className="panel padded" aria-live="polite"><h2>Hasil Preprocessing · {report.name}</h2><p>Status dataset: <strong>{report.status}</strong> · Kualitas data: <strong>{report.ready?"Lulus":"Tidak lulus"}</strong></p><div className="metric-grid"><Metric label="Null" value={report.null_cells}/><Metric label="Invalid" value={report.invalid_cells}/><Metric label="Duplikat" value={report.duplicate_rows}/></div><p className="muted small">Kolom hilang: {report.missing_columns?.join(", ")||"Tidak ada"}</p></section>}
    {selected&&<section className="panel padded"><div className="panel-title"><h2>Isi {selected.dataset.name}</h2><button onClick={()=>setSelected(null)}>Tutup</button></div><div className="table-wrap"><table><thead><tr>{selected.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{selected.rows.slice(0,20).map((r,i)=><tr key={i}>{selected.columns.map(c=><td key={c}>{String(r[c]??"")}</td>)}</tr>)}</tbody></table></div><p className="muted small">Menampilkan 20 dari maksimal 100 baris preview.</p></section>}
  </>;
}
function Models() {
  const [tick, setTick] = useState(0),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [selected, setSelected] = useState(null);
  const { data, error: loadError } = useLoad("/admin/model-versions", tick);
  const { data: jobs } = useLoad("/admin/training-jobs", tick);
  const { data: activeData } = useLoad("/admin/models/active", tick);
  const { data: datasetData } = useLoad("/datasets", tick);
  const models = list(data, "models");
  const datasets = list(datasetData, "items");
  const jobList = list(jobs, "jobs");
  const [datasetId, setDatasetId] = useState("");
  const [trainingJob, setTrainingJob] = useState(null);
  async function trainDataset() {
    if (!datasetId) return;
    try { setTrainingJob(await post(`/datasets/${datasetId}/train`)); setTick(tick + 1); }
    catch (e) { setError(e.message); }
  }
  async function editModel(model) {
    const name = prompt("Nama model", model.name || model.algorithm);
    if (!name?.trim()) return;
    try { await api(`/admin/model-versions/${model.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) }); setTick(tick + 1); }
    catch (e) { setError(e.message); }
  }
  async function deleteModel(model) {
    if (!confirm(`Delete model ${model.name || model.algorithm}?`)) return;
    try { await api(`/admin/model-versions/${model.id}`, { method: "DELETE" }); setTick(tick + 1); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => {
    if (!jobList.some((j) => ["queued", "running"].includes(j.status))) return;
    const t = setInterval(() => setTick((t) => t + 1), 2500);
    return () => clearInterval(t);
  }, [JSON.stringify(jobList)]);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">EKSPERIMEN & REGISTRY</span>
          <h1>Bandingkan. Evaluasi. Pilih.</h1>
          <p>
            Random Forest dan XGBoost, dengan Logistic Regression sebagai
            baseline.
          </p>
        </div>
      </div>
      <ErrorBox error={error || loadError} />
      {message && <div className="success" role="status">{message}</div>}
      <section className="panel padded">
        <span className="eyebrow">TRAINING</span>
        <h2>Training Dataset</h2>
        <p>Pilih dataset berstatus Ready. Setiap dataset hanya dapat satu kali training sukses.</p>
        <div className="actions">
          <label>Pilih dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">Pilih dataset…</option>
              {datasets.map((d) => <option key={d.id} value={d.id} disabled={d.status !== "ready"}>{d.name} · {d.status}</option>)}
            </select>
          </label>
          <button className="primary" disabled={!datasetId || jobList.some((j) => ["queued", "running"].includes(j.status))} onClick={trainDataset}>Training</button>
        </div>
        {trainingJob && <p role="status">Job {trainingJob.id?.slice(0, 8)} masuk antrean.</p>}
        {(() => {
          const completed = jobList.find((j) => j.status === "completed" && j.result);
          if (!completed) return null;
          const result = typeof completed.result === "string" ? JSON.parse(completed.result) : completed.result;
          const best = result?.best, version = result?.all_versions?.[best]?.version;
          const implemented = Object.values(activeData?.active || {}).some((item) => item?.id === version);
          return <div className="panel-title"><div><h3>Champion hasil training</h3><p>{best || "—"} · {version || "—"}</p></div><button className="primary" disabled={!version || implemented} onClick={async()=>{setError("");setMessage("");try{await post(`/admin/model-versions/${version}/implement`);setMessage("Champion berhasil diimplementasikan sebagai Main Model.");setTick(t=>t+1)}catch(e){setError(e.message)}}}>{implemented ? "Sudah Diimplementasikan" : "Implementasikan"}</button></div>;
        })()}
      </section>
      <section className="panel padded">
        <span className="eyebrow">MAIN MODEL</span>
        <h2>Main Model</h2>
        {(() => {
          const active = Object.values(activeData?.active || {});
          const main = active.find((item) => item?.id) || {};
          return <>
            <p><strong>{main.algorithm || "Belum ada model aktif"}</strong></p>
            <p className="muted small">{main.id || "Implementasikan model terbaik dari hasil training."}</p>
          </>;
        })()}
      </section>
      <section className="panel">
        <div className="panel-title">
          <div>
            <span className="eyebrow">PERBANDINGAN MODEL</span>
            <h2>Perbandingan Model</h2>
            <p>Split dan seed yang sama. Macro F1 sebagai metrik utama.</p>
          </div>
          <span className="counter">{models.length} versi</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model / versi</th>
                <th>Macro F1</th>
                <th>Recall Dropout</th>
                <th>Balanced acc.</th>
                <th>Log Loss</th>
                <th>ECE</th>
                <th>Status</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => {
                const v = m.metrics?.test || m.metrics || {};
                return (
                  <tr key={m.id}>
                    <td>
                      <button
                        className="text-button"
                        onClick={() =>
                          setSelected(m)
                        }
                      >
                        {m.algorithm || m.name}
                      </button>
                      <small>{m.id}</small>
                    </td>
                    <td className="number">{v.macro_f1?.toFixed(3) ?? "—"}</td>
                    <td>{v.recall_dropout?.toFixed(3) ?? "—"}</td>
                    <td>{v.balanced_accuracy?.toFixed(3) ?? "—"}</td>
                    <td>{v.log_loss?.toFixed(3) ?? "—"}</td>
                    <td>{v.ece?.toFixed(3) ?? "—"}</td>
                    <td>
                      <Badge
                        value={m.experimental ? "experimental" : m.status}
                      />
                    </td>
                    <td>
                      {m.status === "champion" ? (
                        <span className="muted small">Main Model dilindungi</span>
                      ) : (
                        <div className="actions">
                          <button onClick={() => editModel(m)}>Edit</button>
                          <button className="danger" onClick={() => deleteModel(m)}>Delete</button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!models.length && (
            <Empty>
              Belum ada model untuk tahap ini. Mulai training untuk membuat
              perbandingan nyata.
            </Empty>
          )}
        </div>
      </section>
      {selected && (
        <section className="panel padded">
          <div className="panel-title">
            <h2>Evaluasi {selected.algorithm}</h2>
            <button
              className="icon-button"
              aria-label="Tutup evaluasi"
              onClick={() => setSelected(null)}
            >
              <X size={18} />
            </button>
          </div>
          <h3>Confusion matrix</h3>
          <p className="muted small">
            Baris: kelas aktual. Kolom: kelas prediksi.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Aktual / Prediksi</th>
                  {["Dropout", "Enrolled", "Graduate"].map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(
                  selected.metrics?.test?.confusion_matrix ||
                  selected.metrics?.confusion_matrix ||
                  []
                ).map((row, i) => (
                  <tr key={i}>
                    <th>{["Dropout", "Enrolled", "Graduate"][i]}</th>
                    {row.map((n, j) => (
                      <td key={j}>{n}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ModelEvaluation model={selected} />

          <p className="muted small">
            Performa dataset UCI tidak membuktikan validitas untuk mahasiswa
            Indonesia.
          </p>
        </section>
      )}
      <section className="panel padded">
        <h2>Aktivitas training</h2>
        {jobList.map((j) => (
          <div className="timeline-item" key={j.id}>
            <div>
              <strong>{stageName(j.stage)}</strong>
              <small>
                {date(j.created_at)} · {j.progress || 0}%
              </small>
            </div>
            <Badge value={j.status} />

            {j.error && <span className="red">{j.error}</span>}
            {!["queued", "running"].includes(j.status) && (
              <button className="danger" onClick={async()=>{if(!confirm("Hapus hasil training dan kembalikan dataset ke Ready?"))return;setError("");setMessage("");try{await api(`/admin/training-jobs/${j.id}`,{method:"DELETE"});setDatasetId("");setMessage("Training berhasil dihapus. Dataset siap dipilih kembali.");setTick(t=>t+1)}catch(e){setError(e.message)}}}>Hapus Training</button>
            )}
          </div>
        ))}
        {!jobList.length && <Empty>Belum ada job training.</Empty>}
      </section>
    </>
  );
}
function UsersAdmin() {
  const [tab, setTab] = useState("users"),
    [tick, setTick] = useState(0),
    [error, setError] = useState(""),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      role: "advisor",
    }),
    [assign, setAssign] = useState({ advisor_id: "", student_id: "" }),
    [move, setMove] = useState({ student_id: "", advisor_id: "" });
  const { data, error: loadError } = useLoad(
    tab === "users" ? "/admin/users" : "/admin/audit",
    tick,
  );
  const { data: assignData } = useLoad("/admin/assignments", tick);
  const assignments = list(assignData, "items"),
    advisorList = list(assignData, "advisors"),
    maxBimbingan = assignData?.max_bimbingan ?? 5;
  const rows = list(data, tab === "users" ? "users" : "events");
  async function create(e) {
    e.preventDefault();
    try {
      await post("/admin/users", form);
      setForm({ name: "", email: "", password: "", role: "advisor" });
      setTick(tick + 1);
    } catch (e) {
      setError(e.message);
    }
  }
  async function assignment(e) {
    e.preventDefault();
    try {
      await post("/admin/assignments", {
        ...assign,
        advisor_id: Number(assign.advisor_id),
      });
      setError("");
      setAssign({ ...assign, student_id: "" });
      setTick(tick + 1);
    } catch (e) {
      setError(e.message);
    }
  }
  async function lepas(sid) {
    try {
      await api(`/admin/assignments?student_id=${encodeURIComponent(sid)}`, {
        method: "DELETE",
      });
      setError("");
      setTick(tick + 1);
    } catch (e) {
      setError(e.message);
    }
  }
  async function ganti(e) {
    e.preventDefault();
    try {
      await api("/admin/assignments", {
        method: "PATCH",
        body: JSON.stringify({
          student_id: move.student_id,
          advisor_id: Number(move.advisor_id),
        }),
      });
      setError("");
      setMove({ student_id: "", advisor_id: "" });
      setTick(tick + 1);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADMINISTRASI</span>
          <h1>Pengguna & audit</h1>
          <p>Akses yang jelas, aktivitas yang dapat ditelusuri.</p>
        </div>
      </div>
      <div className="segmented">
        <button
          className={tab === "users" ? "selected" : ""}
          onClick={() => setTab("users")}
        >
          Pengguna
        </button>
        <button
          className={tab === "audit" ? "selected" : ""}
          onClick={() => setTab("audit")}
        >
          Audit log
        </button>
      </div>
      <ErrorBox error={error || loadError} />
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {(tab === "users"
                  ? ["Nama", "Email", "Peran", "Status"]
                  : ["Waktu", "Aktor", "Aksi", "Resource", "Hasil"]
                ).map((t) => (
                  <th key={t}>{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id || i}>
                  {tab === "users" ? (
                    <>
                      <td>{r.name}</td>
                      <td>{r.email}</td>
                      <td>
                        <Badge value={r.role} />
                      </td>
                      <td>
                        <button
                          onClick={async () => {
                            if (!confirm(`Ubah status akun ${r.email}?`))
                              return;
                            try {
                              await api(`/admin/users/${r.id}`, {
                                method: "PATCH",
                                body: JSON.stringify({
                                  status:
                                    r.status === "disabled"
                                      ? "active"
                                      : "disabled",
                                }),
                              });
                              setTick(tick + 1);
                            } catch (e) {
                              setError(e.message);
                            }
                          }}
                        >
                          {r.status === "disabled" ? "Aktifkan" : "Nonaktifkan"}
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{date(r.created_at || r.timestamp)}</td>
                      <td>{r.actor || r.actor_id || "—"}</td>
                      <td>{r.action}</td>
                      <td>
                        {r.resource} {r.resource_id}
                      </td>
                      <td>{r.outcome}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty />}
        </div>
      </section>
      {tab === "audit" && (
        <a className="button" href="/api/admin/audit/export">
          Ekspor audit CSV
        </a>
      )}

      {tab === "users" && (
        <div className="two-columns">
          <form className="panel padded" onSubmit={create}>
            <h2>Tambah pengguna</h2>
            {[
              ["name", "Nama", "text"],
              ["email", "Email", "email"],
              ["password", "Password awal", "password"],
            ].map(([key, label, type]) => (
              <label key={key}>
                {label}
                <input
                  type={type}
                  required
                  minLength={key === "password" ? 12 : 1}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </label>
            ))}
            <label>
              Peran
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="advisor">Dosen Wali</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <button className="primary">Simpan pengguna</button>
          </form>
          <form className="panel padded" onSubmit={assignment}>
            <h2>Penugasan mahasiswa</h2>
            <p className="muted small">
              Satu mahasiswa hanya punya satu dosen wali. Batas {maxBimbingan}{" "}
              mahasiswa per dosen.
            </p>
            <label>
              Dosen Wali
              <select
                required
                value={assign.advisor_id}
                onChange={(e) =>
                  setAssign({ ...assign, advisor_id: e.target.value })
                }
              >
                <option value="">Pilih dosen…</option>
                {rows
                  .filter((r) => r.role !== "admin")
                  .map((r) => {
                    const n =
                      advisorList.find((a) => a.id === r.id)?.n ??
                      assignments.filter((a) => a.advisor_id === r.id).length;
                    return (
                      <option key={r.id} value={r.id} disabled={n >= maxBimbingan}>
                        {r.name} — {n}/{maxBimbingan}
                        {n >= maxBimbingan ? " (penuh)" : ""}
                      </option>
                    );
                  })}
              </select>
            </label>
            <label>
              ID mahasiswa
              <input
                required
                value={assign.student_id}
                onChange={(e) =>
                  setAssign({ ...assign, student_id: e.target.value })
                }
              />
            </label>
            <button className="primary">Simpan penugasan</button>
          </form>
          <form className="panel padded" onSubmit={ganti}>
            <h2>Ganti dosen wali</h2>
            <p className="muted small">
              Pindahkan mahasiswa ke dosen lain tanpa melepas lebih dulu.
            </p>
            <label>
              ID mahasiswa
              <input
                required
                value={move.student_id}
                onChange={(e) => setMove({ ...move, student_id: e.target.value })}
              />
            </label>
            <label>
              Dosen wali baru
              <select
                required
                value={move.advisor_id}
                onChange={(e) => setMove({ ...move, advisor_id: e.target.value })}
              >
                <option value="">Pilih dosen…</option>
                {advisorList.map((a) => (
                  <option key={a.id} value={a.id} disabled={a.n >= maxBimbingan}>
                    {a.name} — {a.n}/{maxBimbingan}
                    {a.n >= maxBimbingan ? " (penuh)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary">Pindahkan</button>
          </form>
        </div>
      )}
      {tab === "users" && (
        <section className="panel padded">
          <div className="panel-title">
            <div>
              <h2>Daftar penugasan</h2>
              <p className="muted small">
                {assignments.length} mahasiswa sudah punya dosen wali. Lepas
                untuk mengosongkan.
              </p>
            </div>
          </div>
          {assignments.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID Mahasiswa</th>
                    <th>Dosen wali</th>
                    <th>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {assignments.map((a) => (
                    <tr key={a.student_id}>
                      <td>{a.student_id}</td>
                      <td>{a.advisor_name || "—"}</td>
                      <td>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => setMove({ student_id: a.student_id, advisor_id: "" })}
                        >
                          Ganti
                        </button>{" "}
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => lepas(a.student_id)}
                        >
                          Lepas
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">
              Belum ada mahasiswa yang ditetapkan. Semua dosen wali masih kosong.
            </p>
          )}
        </section>
      )}
    </>
  );
}
function App() {
  const [user, setUser] = useState(null),
    [ready, setReady] = useState(false),
    [page, setPage] = useState("dashboard"),
    [student, setStudent] = useState(null),
    [handlingStudent, setHandlingStudent] = useState(""),
    [menu, setMenu] = useState(false);
  useEffect(() => {
    api("/auth/me")
      .then((d) => setUser(d.user || null))
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  if (!ready)
    return (
      <div className="boot">
        SPRAM<span>Memuat ruang kerja…</span>
      </div>
    );
  if (!user) return <Login onLogin={setUser} />;
  const nav = (n) => {
    setPage(n);
    setStudent(null);
    setMenu(false);
  };
  async function logout() {
    try {
      await post("/auth/logout");
      setUser(null);
      await api("/auth/me");
    } catch (e) {
      alert(e.message);
    }
  }
  return (
    <div className="app">
      <a className="skip-link" href="#content">
        Lewati ke konten
      </a>
      {menu && (
        <button
          className="backdrop"
          aria-label="Tutup navigasi"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <div className="brand">
          <GraduationCap size={30} />
          <span>
            SPRAM<span className="brand-sub">ACADEMIC SUPPORT SYSTEM</span>
          </span>
        </div>
        <div className="workspace">
          <span className="workspace-icon">A</span>
          <div>
            Ruang akademik
            <small>
              {user.role === "admin"
                ? "Administrator"
                : "Dosen Pembimbing Akademik"}
            </small>
          </div>
        </div>
        <span className="nav-caption">RUANG KERJA</span>
        <nav>
          {navigation
            .filter(
              ([key]) =>
                user.role === "admin"
                  ? key !== "handling"
                  : !ADMIN_PAGES.includes(key),
            )
            .map(([key, label, Icon]) => (
              <button
                key={key}
                className={page === key ? "active" : ""}
                onClick={() => nav(key)}
              >
                <Icon size={19} />
                {label}
              </button>
            ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user">
            <span className="avatar">{user.name?.[0] || "A"}</span>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role === "admin" ? "Admin" : "Dosen Wali"}</small>
            </div>
          </div>
          <button onClick={logout}>
            <LogOut size={17} />
            Keluar
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Buka navigasi"
            onClick={() => setMenu(true)}
          >
            <Menu />
          </button>
          <div>
            <strong>{navigation.find((n) => n[0] === page)?.[1]}</strong>
            <small>
              Ruang kerja /{" "}
              {student || navigation.find((n) => n[0] === page)?.[1]}
            </small>
          </div>
          <div className="topbar-meta">
            <span className="prototype">Prototipe akademik</span>
            <span className="avatar small-avatar">{user.name?.[0] || "A"}</span>
          </div>
        </header>
        <main id="content" tabIndex="-1">
          {student ? (
            <StudentDetail
              id={student}
              user={user}
              onClose={() => setStudent(null)}
              onOpenHandling={(sid) => {
                setStudent(null);
                setHandlingStudent(sid);
                nav("handling");
              }}
            />
          ) : page === "dashboard" ? (
            <Dashboard onNavigate={nav} onStudent={setStudent} />
          ) : page === "students" ? (
            <StudentDirectory onStudent={setStudent} user={user} />
          ) : page === "handling" && user.role === "advisor" ? (
            <Penanganan initialStudent={handlingStudent} user={user} />
          ) : page === "predict" ? (
            <Predict user={user} />
          ) : page === "batch" ? (
            <Batch />
          ) : page === "rules" && user.role === "admin" ? (
            <RulesAdmin />
          ) : page === "models" ? (
            <Models />
          ) : page === "llm" && user.role === "admin" ? (
            <LlmSettings />
          ) : page === "users" ? (
            <UsersAdmin />
          ) : null}
          <footer className="page-footer">
            <span>SPRAM · Pendampingan berbasis data</span>
            <span>UCI Academic Success / CC BY 4.0</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
