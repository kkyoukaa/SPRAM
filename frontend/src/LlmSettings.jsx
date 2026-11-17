// Pengaturan model: kelola penyedia custom + pilih model aktif.
import React, { useEffect, useState } from "react";
import { AlertCircle, Cpu, Plus, RefreshCw, Trash2, Check, Search } from "lucide-react";
import { api, list } from "./api";

const KOSONG = { name: "", base_url: "", api_key: "" };
const BATAS_TAMPIL = 60;

export default function LlmSettings() {
  const [providers, setProviders] = useState([]);
  const [active, setActive] = useState(null);
  const [form, setForm] = useState(KOSONG);
  const [models, setModels] = useState({});
  const [picked, setPicked] = useState({});
  const [cari, setCari] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const d = await api("/admin/llm/providers");
      const items = list(d, "items");
      setProviders(items);
      setActive(d.active || null);
      // tarik daftar model otomatis supaya kotak cari langsung terisi
      for (const p of items) {
        if (!p.model_count) continue;
        try {
          const m = await api(`/admin/llm/providers/${p.id}/models`);
          setModels((prev) => ({ ...prev, [p.id]: list(m, "items") }));
        } catch {
          /* biarkan tombol "Muat model" yang menangani */
        }
      }
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    api("/admin/llm/active").then(setActive).catch(() => {});
  }, []);

  async function simpan(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const d = await api("/admin/llm/providers", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setMessage(
        `Penyedia "${d.name}" disimpan. ${d.model_count} model terbaca dari endpoint.`,
      );
      setForm(KOSONG);
      await load();
      if (d.models?.length) setModels((m) => ({ ...m, [d.id]: d.models }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function muatModel(pid) {
    setError("");
    try {
      const d = await api(`/admin/llm/providers/${pid}/models`);
      setModels((m) => ({ ...m, [pid]: list(d, "items") }));
      setMessage(`${d.count} model dimuat ulang.`);
    } catch (e) {
      setError(e.message);
    }
  }

  async function pilihModel(pid, model) {
    setError("");
    setMessage("");
    try {
      const d = await api("/admin/llm/active", {
        method: "POST",
        body: JSON.stringify({ provider_id: pid, model }),
      });
      setMessage(`Model aktif: ${d.model}. Uji jawaban: "${d.probe}"`);
      const a = await api("/admin/llm/active");
      setActive(a);
    } catch (e) {
      setError(e.message);
    }
  }

  async function buang(pid, nama) {
    if (!confirm(`Hapus penyedia "${nama}"? Model aktif akan dikosongkan.`)) return;
    setError("");
    try {
      await api(`/admin/llm/providers/${pid}`, { method: "DELETE" });
      setMessage(`Penyedia "${nama}" dihapus.`);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PENGATURAN MODEL</span>
          <h1>Penyedia & model AI</h1>
          <p>
            Tambahkan endpoint OpenAI-compatible, tarik daftar modelnya, lalu
            pilih satu model untuk percakapan dosen wali.
          </p>
        </div>
        {active?.model && (
          <span className="badge champion">
            <Cpu size={14} /> {active.model}
          </span>
        )}
      </div>

      {error && (
        <div className="error" role="alert">
          <AlertCircle size={18} /> {error}
        </div>
      )}
      {message && <p role="status" className="muted">{message}</p>}

      <div className="two-columns">
        <form className="panel padded" onSubmit={simpan}>
          <h2>Tambah penyedia</h2>
          <p className="muted small">
            Endpoint harus OpenAI-compatible (`/v1/models` dan
            `/v1/chat/completions`). API key disimpan terenkripsi dan tidak
            pernah ditampilkan kembali.
          </p>
          <label>
            Nama penyedia
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Contoh: Gateway Internal"
            />
          </label>
          <label>
            Base URL
            <input
              required
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder="http://10.168.20.228:20128/v1"
            />
          </label>
          <label>
            API key
            <input
              required
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="Bearer token"
            />
          </label>
          <button className="primary" disabled={busy}>
            <Plus size={16} /> {busy ? "Menghubungi endpoint…" : "Simpan & tarik model"}
          </button>
        </form>

        <section className="panel padded">
          <h2>Model aktif</h2>
          {active?.model ? (
            <>
              <p className="small">
                <strong>{active.model}</strong>
                <br />
                <span className="muted">
                  {active.provider_name} · {active.model_count} model tersedia
                </span>
              </p>
              <p className="muted small">
                Digunakan oleh chatbot dosen wali. Bila endpoint gagal, chatbot
                menjawab dengan mode terbatas dan mengatakannya.
              </p>
            </>
          ) : (
            <p className="muted">
              Belum ada model aktif. Pilih satu dari daftar penyedia di bawah.
            </p>
          )}
        </section>
      </div>

      <section className="panel padded">
        <h2>Daftar penyedia</h2>
        {!providers.length && (
          <p className="muted">Belum ada penyedia. Tambahkan lewat form di atas.</p>
        )}
        {providers.map((p) => {
          const daftar = models[p.id] || [];
          const kata = (cari[p.id] || "").trim().toLowerCase();
          const tersaring = kata
            ? daftar.filter(
                (m) =>
                  m.id.toLowerCase().includes(kata) ||
                  (m.owned_by || "").toLowerCase().includes(kata),
              )
            : daftar;
          const terpilih = picked[p.id] || active?.model || "";
          return (
            <div className="llm-provider" key={p.id}>
              <div className="panel-title">
                <div>
                  <strong>{p.name}</strong>
                  <p className="muted small">
                    {p.base_url} · kunci {p.api_key_masked} · {p.model_count} model
                  </p>
                </div>
                <div>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => muatModel(p.id)}
                  >
                    <RefreshCw size={14} /> Muat model
                  </button>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => buang(p.id, p.name)}
                  >
                    <Trash2 size={14} /> Hapus
                  </button>
                </div>
              </div>
              <div className="llm-model-row">
                <div className="llm-search">
                  <Search size={15} className="llm-search-icon" />
                  <input
                    value={cari[p.id] || ""}
                    onChange={(e) =>
                      setCari({ ...cari, [p.id]: e.target.value })
                    }
                    placeholder="Cari model… (mis. deepseek)"
                    aria-label={`Cari model ${p.name}`}
                    autoComplete="off"
                  />
                  {(cari[p.id] || "") && (
                    <button
                      type="button"
                      className="llm-search-clear"
                      aria-label="Bersihkan pencarian"
                      onClick={() => setCari({ ...cari, [p.id]: "" })}
                    >
                      ×
                    </button>
                  )}
                </div>
                <button
                  className="primary"
                  disabled={!terpilih}
                  onClick={() => pilihModel(p.id, terpilih)}
                >
                  <Check size={16} /> Pakai model ini
                </button>
              </div>

              {daftar.length > 0 && (
                <div className="llm-results">
                  <p className="muted small llm-results-count">
                    {tersaring.length} dari {daftar.length} model
                    {tersaring.length > BATAS_TAMPIL &&
                      ` · menampilkan ${BATAS_TAMPIL} pertama, perjelas kata kunci`}
                  </p>
                  <ul className="llm-list" role="listbox" aria-label={`Daftar model ${p.name}`}>
                    {tersaring.slice(0, BATAS_TAMPIL).map((m) => (
                      <li key={m.id}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={terpilih === m.id}
                          className={`llm-item ${terpilih === m.id ? "selected" : ""}`}
                          onClick={() =>
                            setPicked({ ...picked, [p.id]: m.id })
                          }
                        >
                          <span className="llm-item-id">{m.id}</span>
                          {m.owned_by && (
                            <span className="llm-item-owner">{m.owned_by}</span>
                          )}
                          {terpilih === m.id && <Check size={14} />}
                        </button>
                      </li>
                    ))}
                    {!tersaring.length && (
                      <li className="llm-empty">
                        Tidak ada model yang cocok dengan “{cari[p.id]}”.
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </section>
    </>
  );
}
