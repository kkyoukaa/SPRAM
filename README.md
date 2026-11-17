# SPRAM

Sistem Prediksi Risiko Akademik Mahasiswa (SPRAM) adalah prototipe akademik untuk memberi sinyal risiko dan mendukung pendampingan mahasiswa. Dataset eksperimen: UCI *Predict Students' Dropout and Academic Success* (ID 697, CC BY 4.0). Data berasal dari Portugal; hasilnya **belum membuktikan validitas pada mahasiswa Indonesia**. Sistem bukan alat keputusan otomatis untuk penerimaan, sanksi, beasiswa, kelulusan, atau status akademik. Jangan masukkan data mahasiswa nyata tanpa izin dan pengamanan yang sesuai.

## Struktur proyek

| Lokasi | Isi |
| --- | --- |
| `backend/` | API Flask, pipeline prediksi, SQLite, sistem pakar, kamus, dan server frontend. |
| `frontend/` | Dashboard React/Vite untuk Admin dan Dosen Wali. |
| `scripts/` | Pelatihan, penyajian aplikasi, dan pembuatan data rujukan. |
| `tests/` | Pengujian backend. |
| `docs/api.json` | Kontrak API. |
| `docs/acceptance.md` | Kriteria penerimaan dan bukti verifikasi. |
| `docs/v2.md` | Aturan, ambang, contoh penelusuran, serta batasan sistem pakar. |
| `docs/screenshots/` | Tangkapan layar QA. |
| `data/` | Dataset unggahan, SQLite, dan kredensial demo lokal; **tidak untuk Git**. |
| `artifacts/` | Model dan metrik eksperimen lokal; **tidak untuk Git**. |

Folder proyek ini bernama `file-server-up-github/`, di dalam `/home/haruu/Project/Web/Proyek Kecerdasan Buatan/` (nama direktori induk memang mengandung spasi). Folder ini **belum memiliki repository Git**; jalankan `git init` di sini jika ingin menjadikannya akar repository sebelum push. Berkas di dalamnya merupakan salinan kode sumber; data dan kredensial lokal tidak disertakan. `data.csv` asli dan dokumen PRD berada satu tingkat di atas folder ini pada tata letak lokal; keduanya tidak otomatis termasuk saat folder ini dijadikan repository dan di-push. Unduh dataset dari UCI Machine Learning Repository, lalu tempatkan sebagai `../data.csv` atau berikan path lewat `--dataset` saat melatih. Dataset memakai pemisah titik koma (`;`) dan berisi 4.424 baris, 36 fitur serta label `Target`. SHA-256 berkas yang digunakan dalam laporan: `3ef126de5cefff26eb11fbb4237f1a1401cb64b488e2f1d598c23cedeb4c45ae`. Pastikan lisensi dataset dipatuhi; jangan unggah data privat.

## Persyaratan

Python 3.11, Node.js dan npm, serta akses ke dataset untuk pelatihan. Dependensi Python dipatok di `requirements.txt`; dependensi frontend di `frontend/package.json` dan lockfile. Masuk ke folder proyek dengan `cd "/home/haruu/Project/Web/Proyek Kecerdasan Buatan/file-server-up-github"`; tanda kutip wajib karena nama direktori induk mengandung spasi. Perintah di bawah dijalankan dari folder tersebut, kecuali yang memakai `cd frontend`.

## Menyiapkan dan menjalankan

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
.venv/bin/python scripts/train.py --stage all --dataset ../data.csv
.venv/bin/python scripts/serve.py
```

Buka `http://localhost:5000/` setelah server siap. `scripts/serve.py` mengikat `0.0.0.0:5000`: jalankan hanya di jaringan tepercaya atau batasi akses dengan firewall/reverse proxy; ini server pengembangan, bukan konfigurasi produksi. Pada startup pertama, aplikasi membuat database dan kredensial demo acak di `data/demo-credentials.txt` dengan izin berkas 0600. Baca berkas tersebut **secara lokal** untuk login; jangan commit, kirim, atau tempel kredensial ke laporan. Jangan menjalankan pelatihan ulang hanya untuk membuka aplikasi bila artefak model yang sah sudah tersedia.

Jika dataset berada di path lain:

```bash
.venv/bin/python scripts/train.py --stage all --dataset /path/ke/data.csv
```

Aplikasi secara bawaan mencari dataset di `../data.csv` untuk tugas pelatihan dari UI. Jika menempatkan dataset di tempat lain, jalankan pelatihan lewat CLI seperti di atas; sesuaikan konfigurasi aplikasi bila fitur pelatihan dari UI akan dipakai.

## Eksperimen dan bukti hasil

Ada dua tahap: `intake` memakai 24 fitur nonsemester, `academic_update` memakai 36 fitur sampai semester dua. Masing-masing membandingkan Logistic Regression, Random Forest, dan XGBoost. Split terstratifikasi 85:15 dengan seed 42 menghasilkan 3.760 baris latih dan 664 baris uji. Validasi silang tiga lipatan pada data latih bukan tiga pengulangan independen. Artefak yang tersedia mencatat **satu pelatihan per tahap**, bukan eksperimen multi-seed. Jangan mengklaim simpangan baku antarpengulangan atau generalisasi ke populasi baru.

Setelah melatih, periksa `artifacts/<tahap>-<algoritma>-<versi>/metrics.json` untuk Macro F1 CV, Macro F1 uji, balanced accuracy, recall Dropout, log loss, ECE, confusion matrix, dan recall per kelas. `metadata.json` mencatat seed, fitur, dan checksum dataset; `calibration.json` memuat evaluasi kalibrasi. Lampiran D laporan merangkum keenam skenario. Isi `artifacts/` tidak diunggah ke Git; untuk audit angka asli, salin artefak lewat jalur privat yang disetujui atau jalankan ulang pelatihan dengan dataset yang sama. Pelatihan ulang tidak menjamin metadata waktu maupun ID artefak sama.

Pemilihan kandidat di hasil eksperimen tidak sama dengan aktivasi otomatis Main Model. Promosi model untuk aplikasi dilakukan melalui alur Admin dan audit log.

## Lapisan aturan dan penjelasan

`backend/dictionary.json` dan `backend/dictionary.py` menerjemahkan label fitur serta nilai kode. `backend/expert.py` memuat delapan aturan dan forward chaining. Halaman Detail Mahasiswa menampilkan risiko, faktor, konsultasi, dan tindak lanjut. Status penanganan (`cases`) terpisah dari risiko model. Fitur sensitif dan makro tidak diizinkan sebagai kondisi aturan. Rincian: `docs/v2.md`.

Bangun ulang data rujukan atau periksa kamus bila memang diperlukan:

```bash
.venv/bin/python scripts/build_reference_data.py
.venv/bin/python scripts/build_dictionary.py
.venv/bin/python scripts/check_dictionary.py
```

## Pengujian

```bash
.venv/bin/python -m pytest tests -q
cd frontend && npm run build && node test-format.mjs
```

Ikuti `docs/acceptance.md` untuk kriteria penerimaan. Lulus unit test tidak berarti siap produksi; periksa RBAC backend, persistensi setelah restart, batch parsial, formula injection, promosi/rollback, aksesibilitas, dan performa. Tampilan waktu menggunakan Asia/Jakarta (WIB), sedangkan database menyimpan UTC.

## Keamanan saat push GitHub

`.gitignore` mengecualikan `data/`, `artifacts/`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `.env`, dan log. Setelah menjalankan `git init` di folder proyek ini, periksa `git status` sebelum push; file di luar folder repository (`../data.csv`, dokumen laporan) tidak masuk otomatis. **Jangan commit** kredensial, database SQLite, dataset mahasiswa, kunci API, model artefak privat, atau `.env`. URL repository belum dicantumkan karena belum ada alamat GitHub yang diberikan; setelah push, salin URL repository ke Lampiran G bila dibutuhkan.
