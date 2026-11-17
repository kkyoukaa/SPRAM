import React, { useEffect, useState } from "react";
import { api, post, list } from "./api";
import { Plus, Save, AlertCircle } from "lucide-react";

const emptyRule = () => ({
  rule_id: "",
  nama: "",
  hipotesis: "",
  pertanyaan: "",
  prioritas: 99,
  topik: "umum",
  aktif: 1,
  kondisi_text: "[]",
  kondisi_atau_text: "[]",
  tindakan_text: '{"ya":[],"tidak":[],"belum_tahu":[]}',
});

function toForm(r) {
  return {
    rule_id: r.rule_id,
    nama: r.nama,
    hipotesis: r.hipotesis,
    pertanyaan: r.pertanyaan,
    prioritas: r.prioritas,
    topik: r.topik || "umum",
    aktif: r.aktif,
    kondisi_text: JSON.stringify(r.kondisi || [], null, 1),
    kondisi_atau_text: JSON.stringify(r.kondisi_atau || [], null, 1),
    tindakan_text: JSON.stringify(r.tindakan || {}, null, 1),
  };
}

function parse(text, fallback) {
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

export default function RulesAdmin() {
  const [rules, setRules] = useState([]);
  const [thresholds, setThresholds] = useState(null);
  const [scope, setScope] = useState(null);
  const [scopeMsg, setScopeMsg] = useState("");
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api("/rules")
      .then((d) => {
        setRules(list(d, "items"));
        setThresholds(d.thresholds);
        setScope(d.chat_scope || null);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [tick]);

  async function simpanBatas(e) {
    e.preventDefault();
    setError("");
    setScopeMsg("");
    try {
      const d = await api("/rules/chat-scope", {
        method: "PUT",
        body: JSON.stringify(scope),
      });
      setScope(d);
      setScopeMsg("Batasan percakapan tersimpan. Berlaku untuk percakapan berikutnya.");
    } catch (err) {
      setError(err.message);
    }
  }

  const set = (k, v) => setForm({ ...form, [k]: v });

  async function save(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    const body = {
      rule_id: form.rule_id,
      nama: form.nama,
      hipotesis: form.hipotesis,
      pertanyaan: form.pertanyaan,
      prioritas: Number(form.prioritas),
      topik: form.topik,
      aktif: Number(form.aktif),
      kondisi: parse(form.kondisi_text, []),
      kondisi_atau: parse(form.kondisi_atau_text, []),
      tindakan: parse(form.tindakan_text, {}),
    };
    try {
      if (rules.some((r) => r.rule_id === form.rule_id)) {
        await api(`/rules/${form.rule_id}`, { method: "PATCH", body: JSON.stringify(body) });
        setMessage(`Aturan ${form.rule_id} diperbarui.`);
      } else {
        await post("/rules", body);
        setMessage(`Aturan ${form.rule_id} ditambahkan.`);
      }
      setForm(null);
      setTick((t) => t + 1);
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggle(rule) {
    setError("");
    try {
      if (rule.aktif) {
        await api(`/rules/${rule.rule_id}`, { method: "DELETE" });
        setMessage(`Aturan ${rule.rule_id} dinonaktifkan.`);
      } else {
        await api(`/rules/${rule.rule_id}`, { method: "PATCH", body: JSON.stringify({ aktif: 1 }) });
        setMessage(`Aturan ${rule.rule_id} diaktifkan.`);
      }
      setTick((t) => t + 1);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">BASIS PENGETAHUAN</span>
          <h1>Aturan sistem pakar</h1>
          <p>
            Aturan hanya boleh memakai 36 fitur model. Fitur sensitif dan fitur makro ditolak sebagai
            kondisi.
          </p>
        </div>
        <button className="primary" onClick={() => setForm(emptyRule())}>
          <Plus size={16} /> Aturan baru
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          <AlertCircle size={17} /> {error}
        </div>
      )}
      {message && (
        <div className="success" role="status">
          {message}
        </div>
      )}
      {thresholds && (
        <section className="panel padded">
          <span className="eyebrow">AMBANG ATURAN</span>
          <h2>Ambang dari data latih</h2>
          <p className="muted small">
            Angka di bawah dihitung otomatis dari distribusi {thresholds.dataset_rows?.toLocaleString("id-ID") || "-"} baris
            data latih, bukan ditentukan manual. Persentil 75 berarti 75% mahasiswa nilainya di bawah atau sama
            dengan angka itu; persentil 25 berarti hanya 25% yang nilainya serendah itu.
          </p>
          <div className="ambang-grid">
            {Object.keys(thresholds.meta || thresholds.derivation || {}).map((k) => {
              const m = thresholds.meta?.[k] || {};
              const nilai = Number(thresholds[k]);
              const persen = (k.match(/p(\d+)$/) || [])[1];
              return (
                <article className="ambang" key={k}>
                  <div className="ambang-kepala">
                    <div>
                      <strong>{m.judul || k}</strong>
                      <code>{k}</code>
                    </div>
                    <div className="ambang-nilai">
                      {Number.isFinite(nilai)
                        ? nilai.toLocaleString("id-ID", { maximumFractionDigits: 4 })
                        : String(thresholds[k])}
                      {m.satuan && <small>{m.satuan}</small>}
                    </div>
                  </div>
                  {persen && <span className="ambang-lencana">Persentil {persen}</span>}
                  <p>{m.arti || thresholds.derivation?.[k]}</p>
                  {m.dipakai && (
                    <p className="ambang-pakai">
                      Dipakai di aturan <b>{m.dipakai}</b>
                    </p>
                  )}
                  {m.catatan && <p className="ambang-catatan">{m.catatan}</p>}
                </article>
              );
            })}
          </div>
        </section>
      )}
      {scope && (
        <section className="panel padded">
          <span className="eyebrow">BATASAN PERCAKAPAN</span>
          <h2>Lingkup chatbot dosen wali</h2>
          <p className="muted small">
            Ini yang membatasi obrolan di menu Penanganan. Sejalur dengan aturan di
            bawah — aturan menentukan isi jawaban, batasan ini menentukan apa yang
            boleh dibahas.
          </p>
          <form onSubmit={simpanBatas} className="rule-form">
            <label>
              Yang boleh dibahas
              <textarea
                rows={2}
                value={scope.lingkup || ""}
                onChange={(e) => setScope({ ...scope, lingkup: e.target.value })}
              />
              <small className="muted">
                Contoh: data mahasiswa bimbingan, hasil analisis risiko, dan langkah penanganannya.
              </small>
            </label>
            <label>
              Yang harus ditolak
              <textarea
                rows={3}
                value={scope.ditolak || ""}
                onChange={(e) => setScope({ ...scope, ditolak: e.target.value })}
              />
              <small className="muted">
                Contoh: kode program, konfigurasi server, model AI, API, token, matematika.
              </small>
            </label>
            <label>
              Gaya jawaban
              <input
                value={scope.nada || ""}
                onChange={(e) => setScope({ ...scope, nada: e.target.value })}
              />
              <small className="muted">Contoh: bahasa Indonesia alami, 2-4 kalimat, tanpa format kode.</small>
            </label>
            <label>
              Catatan tambahan
              <textarea
                rows={3}
                value={scope.catatan || ""}
                onChange={(e) => setScope({ ...scope, catatan: e.target.value })}
              />
              <small className="muted">
                Contoh: jangan mengarang identitas, jadwal, atau kebijakan kampus.
              </small>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={scope.aktif !== false}
                onChange={(e) => setScope({ ...scope, aktif: e.target.checked })}
              />
              Batasi topik percakapan (kalau dimatikan, chatbot bebas topik tetapi
              tetap dilarang membocorkan data teknis)
            </label>
            <button className="primary">
              <Save size={16} /> Simpan batasan
            </button>
            {scopeMsg && <p role="status" className="muted small">{scopeMsg}</p>}
          </form>
        </section>
      )}
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Nama</th>
                <th>Hipotesis</th>
                <th>Prioritas</th>
                <th>Status</th>
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.rule_id}>
                  <td>
                    <strong>{r.rule_id}</strong>
                  </td>
                  <td>{r.nama}</td>
                  <td>
                    <span>{r.hipotesis}</span>
                    <small>{r.pertanyaan}</small>
                  </td>
                  <td className="number">{r.prioritas}</td>
                  <td>
                    <span className={`badge ${r.aktif ? "completed" : "failed"}`}>
                      {r.aktif ? "Aktif" : "Nonaktif"}
                    </span>
                  </td>
                  <td>
                    <div className="actions">
                      <button onClick={() => setForm(toForm(r))}>Ubah</button>
                      <button className={r.aktif ? "danger" : ""} onClick={() => toggle(r)}>
                        {r.aktif ? "Nonaktifkan" : "Aktifkan"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rules.length && <p className="muted">Belum ada aturan.</p>}
        </div>
      </section>
      {form && (
        <section className="panel padded">
          <h2>{rules.some((r) => r.rule_id === form.rule_id) ? `Ubah ${form.rule_id}` : "Aturan baru"}</h2>
          <form onSubmit={save} className="rule-form">
            <div className="form-grid">
              <label>
                ID aturan
                <input
                  required
                  value={form.rule_id}
                  disabled={rules.some((r) => r.rule_id === form.rule_id)}
                  onChange={(e) => set("rule_id", e.target.value)}
                  placeholder="R09"
                />
              </label>
              <label>
                Nama
                <input required value={form.nama} onChange={(e) => set("nama", e.target.value)} />
              </label>
              <label>
                Prioritas
                <input
                  type="number"
                  required
                  value={form.prioritas}
                  onChange={(e) => set("prioritas", e.target.value)}
                />
              </label>
              <label>
                Status
                <select value={form.aktif} onChange={(e) => set("aktif", e.target.value)}>
                  <option value={1}>Aktif</option>
                  <option value={0}>Nonaktif</option>
                </select>
              </label>
            </div>
            <label>
              Hipotesis
              <input required value={form.hipotesis} onChange={(e) => set("hipotesis", e.target.value)} />
            </label>
            <label>
              Pertanyaan untuk dosen
              <input required value={form.pertanyaan} onChange={(e) => set("pertanyaan", e.target.value)} />
            </label>
            <label>
              Kondisi (JSON, semua harus benar)
              <textarea
                rows={5}
                value={form.kondisi_text}
                onChange={(e) => set("kondisi_text", e.target.value)}
                placeholder='[{"fitur":"Debtor","op":"==","nilai":1}]'
              />
            </label>
            <label>
              Kondisi alternatif (JSON, salah satu grup benar)
              <textarea
                rows={4}
                value={form.kondisi_atau_text}
                onChange={(e) => set("kondisi_atau_text", e.target.value)}
              />
            </label>
            <label>
              Tindakan per jawaban (JSON)
              <textarea
                rows={5}
                value={form.tindakan_text}
                onChange={(e) => set("tindakan_text", e.target.value)}
              />
            </label>
            <div className="actions">
              <button className="primary">
                <Save size={16} /> Simpan aturan
              </button>
              <button type="button" onClick={() => setForm(null)}>
                Batal
              </button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}
