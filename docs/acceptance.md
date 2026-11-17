# SPRAM — matriks verifikasi PRD

Status awal: implementasi/integrasi berjalan. PASS hanya diisi setelah pengujian nyata.

| Area | Implementasi yang diverifikasi | Status / bukti |
|---|---|---|
| Login | Cookie session, CSRF, role Admin/Dosen, logout | Pending integrasi |
| Scope | Dosen hanya melihat mahasiswa penugasan; bypass API 403 | Pending backend tests |
| Dataset | 4.424 baris, 36 fitur + Target, delimiter semicolon, tidak kosong/duplikat | Diperiksa langsung sebelum implementasi |
| ML | RF, XGBoost, Logistic Regression; Intake 24 / Update 36 | Pending training |
| Evaluasi | Split/seed sama, CV, holdout, kalibrasi, per-kelas, confusion matrix | Pending training |
| Prediksi | Form schema aktif, validasi server, probabilitas, SHAP, provenance | Pending E2E |
| Pembulatan | Tiga probabilitas tampilan tepat 100.0% | PASS `node frontend/test-format.mjs` |
| Batch | Template, validasi, preview, konfirmasi, antrean async, partial, export error/hasil | Pending E2E |
| Riwayat | Snapshot baru tidak menimpa hasil lama | Pending E2E |
| Intervensi | Simpan catatan, tanggal, ubah status | Pending E2E |
| Asisten | Intent allowlist, data tersimpan, fallback | Pending E2E |
| Model Center | Perbandingan RF/XGBoost/baseline per tahap, training, promote, rollback | Pending E2E |
| Admin | Pengguna, penugasan mahasiswa, audit | Pending E2E |
| Ekspor | Scope dan filter, proteksi formula injection | Pending E2E |
| Frontend build | Bundle produksi React/Vite | PASS `npm run build` |
| Dependency frontend | Audit dependency produksi | PASS `npm audit --omit=dev` |
| Login UI | Desktop 1440, mobile 390; form kosong, tanpa overflow/JS error | PASS `node frontend/visual-check.mjs` dengan static server |
| Aksesibilitas dasar | `lang=id`, label form, focus visible, overflow 1280/768/390 | PASS `node frontend/accessibility-check.mjs` |
| Visual | Screenshot tersimpan, pemeriksaan otomatis geometri | Screenshot `docs/screenshots/`; inspeksi gambar manual belum tersedia (vision provider tidak dikonfigurasi) |
| Performance | p95 individu <=3s; batch 5000 <=3m; training <=10m | Belum diukur |
| Operasional | Restart persistence, backup, layanan, runbook | Pending |
| Produksi | TLS, enkripsi at rest, retention, validasi kampus | Tidak boleh diklaim siap produksi tanpa verifikasi terpisah |

## Keputusan implementasi
- Dataset dan PRD sumber tidak diubah.
- Nama header CSV asli dipertahankan; whitespace akhir dinormalisasi.
- Intake tanpa data semester. Status biaya pada Intake adalah asumsi dataset, bukan bukti waktu pencatatan; batasan harus dicantumkan pada model card.
- Tidak ada default fitur tersembunyi. Semua fitur wajib diisi atau dipilih secara eksplisit.
- SHAP menjelaskan output model dasar; probabilitas terkalibrasi harus dilabeli berbeda bila explainer bekerja pada output dasar.
- Eksperimen yang tidak memenuhi gerbang PRD tidak dipromosikan ke dashboard dosen.
- UI menggunakan waktu Asia/Jakarta (WIB).

## Matriks v2 (penjelasan, verifikasi, tindak lanjut)

| Area | Bukti | Status |
|---|---|---|
| Kamus bahasa Indonesia | `scripts/check_dictionary.py` → 36 fitur, 4.424 baris, semua nilai punya teks Indonesia | PASS |
| Detail Mahasiswa | `tests/test_v2.py::test_detail_bahasa_indonesia_dan_profil_lengkap` (36 baris profil, kalimat faktor tanpa nama fitur Inggris) | PASS |
| Sistem pakar | `test_aturan_r01_aktif_dan_r08_hanya_fallback`, `test_aturan_sensitif_dan_makro_ditolak` | PASS |
| Alur menyeluruh | `test_alur_konsultasi_dan_tindak_lanjut` (prediksi → konsultasi → tindakan → ringkasan) | PASS |
| Buka kembali otomatis | `test_prediksi_baru_membuka_kembali_kasus` | PASS |
| Akses dosen | `test_dosen_hanya_melihat_bimbingannya` (403 URL langsung, filter daftar, menu aturan tertutup) | PASS |
| Assign admin | `test_admin_assign_mengubah_lingkup_dosen` | PASS |
| Pengelolaan aturan | `test_admin_dapat_mengelola_aturan` (validasi simpan, nonaktifkan) | PASS |
| Build frontend | `npm run build` | PASS |
