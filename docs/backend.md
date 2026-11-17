# Backend SPRAM

## Menjalankan

```bash
.venv/bin/python scripts/train.py --stage all
.venv/bin/python scripts/serve.py
.venv/bin/python -m pytest tests -q
```

Server Flask melayani API `/api` dan SPA produksi `frontend/dist`. SQLite tersimpan di `data/spram.sqlite`; artefak model berversi tersimpan di `artifacts/`. Akun demo acak dibuat pada startup pertama di `data/demo_credentials.txt` dengan mode `0600`. Hapus database dan file kredensial untuk seed ulang.

## Model

Setiap tahap melatih Logistic Regression, Random Forest, dan XGBoost memakai split stratified seed 42, CV Macro F1, holdout, serta `CalibratedClassifierCV`. Pemilihan memilih model kompleks hanya saat Macro F1 naik minimal 0,02 terhadap baseline LR. Artefak mencakup pipeline, schema, metrics/per-class/confusion matrix, calibration ECE/log-loss, thresholds, background dan konfigurasi explainability, metadata/checksum, serta model card. `n_jobs` dibatasi 2.

Intake memakai 24 fitur nonsemester. Academic Update memakai 36 fitur. Explainability lokal memakai signed dropout probability permutation terhadap median background; payload tetap memakai nama `shap` demi kontrak UI, namun metode dicatat eksplisit di `shap_config.json`.

## Keamanan dan batasan

Semua write memakai `X-CSRF-Token`. Session cookie HttpOnly/SameSite, password di-hash Werkzeug, RBAC admin, dan scope advisor diterapkan backend. Ekspor menghindari CSV formula injection. Untuk deployment HTTPS, set `SPRAM_SECRET_KEY`, aktifkan `SESSION_COOKIE_SECURE`, TLS, rate limiter/reverse proxy, enkripsi disk, backup, serta retention institusi.

Dataset UCI Portugal hanya cocok untuk prototipe akademik. Model belum tervalidasi untuk mahasiswa Indonesia dan tidak boleh dipakai untuk sanksi atau keputusan otomatis.
