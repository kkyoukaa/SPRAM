#!/usr/bin/env python3
"""Bangun backend/dictionary.json dari tabel label 36 fitur + category_labels.json.

Satu sumber istilah Indonesia untuk form prediksi, daftar Mahasiswa, Detail,
dan Konsultasi. Jalankan ulang bila tabel label berubah:

    .venv/bin/python scripts/build_dictionary.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
BACKEND = ROOT / "backend"

DEMOGRAFI, BIAYA, AKADEMIK, MAKRO = (
    "Penerimaan & demografi", "Biaya & ekonomi", "Performa akademik", "Konteks makro")
DAPAT, KONTEKS, SENSITIF = "dapat_ditindaklanjuti", "konteks", "sensitif"

# (nama dataset, label Indonesia, kelompok, jenis faktor, keterangan)
FEATURES = [
    ("Marital status", "Status pernikahan", DEMOGRAFI, SENSITIF, ""),
    ("Application mode", "Jalur pendaftaran", DEMOGRAFI, KONTEKS, ""),
    ("Application order", "Urutan pilihan pendaftaran", DEMOGRAFI, DAPAT, "0 = pilihan pertama, 9 = pilihan terakhir"),
    ("Course", "Program studi", DEMOGRAFI, KONTEKS, ""),
    ("Daytime/evening attendance", "Waktu kuliah", DEMOGRAFI, DAPAT, "Siang / Malam"),
    ("Previous qualification", "Pendidikan sebelumnya", DEMOGRAFI, KONTEKS, ""),
    ("Previous qualification (grade)", "Nilai pendidikan sebelumnya", DEMOGRAFI, KONTEKS, "Skala 0–200"),
    ("Nacionality", "Kewarganegaraan", DEMOGRAFI, SENSITIF, ""),
    ("Mother's qualification", "Pendidikan ibu", DEMOGRAFI, SENSITIF, ""),
    ("Father's qualification", "Pendidikan ayah", DEMOGRAFI, SENSITIF, ""),
    ("Mother's occupation", "Pekerjaan ibu", DEMOGRAFI, SENSITIF, ""),
    ("Father's occupation", "Pekerjaan ayah", DEMOGRAFI, SENSITIF, ""),
    ("Admission grade", "Nilai penerimaan", DEMOGRAFI, KONTEKS, "Skala 0–200"),
    ("Displaced", "Mahasiswa perantau", DEMOGRAFI, DAPAT, "Tinggal jauh dari daerah asal (definisi mengikuti dataset)"),
    ("Educational special needs", "Kebutuhan pendidikan khusus", DEMOGRAFI, SENSITIF, "Ya / Tidak"),
    ("Debtor", "Memiliki tunggakan", BIAYA, DAPAT, "Ya / Tidak"),
    ("Tuition fees up to date", "Biaya kuliah lunas tepat waktu", BIAYA, DAPAT, "Ya / Tidak"),
    ("Gender", "Jenis kelamin", BIAYA, SENSITIF, "Laki-laki / Perempuan"),
    ("Scholarship holder", "Penerima beasiswa", BIAYA, DAPAT, "Ya / Tidak"),
    ("Age at enrollment", "Usia saat mendaftar", BIAYA, KONTEKS, "Tahun"),
    ("International", "Mahasiswa internasional", BIAYA, SENSITIF, "Ya / Tidak"),
] + [
    (f"Curricular units {sem} sem ({kind})", f"Semester {n}: {label}", AKADEMIK, DAPAT, help_text)
    for sem, n in (("1st", 1), ("2nd", 2))
    for kind, label, help_text in (
        ("credited", "unit diakui", "Jumlah unit/mata kuliah yang diakui"),
        ("enrolled", "unit diambil", "Jumlah unit/mata kuliah yang diambil"),
        ("evaluations", "jumlah evaluasi diikuti", "Jumlah evaluasi/ujian yang diikuti"),
        ("approved", "unit lulus", "Jumlah unit/mata kuliah yang lulus"),
        ("grade", "nilai rata-rata", "Skala 0–20, bukan IPK 0–4"),
        ("without evaluations", "unit tanpa evaluasi", "Jumlah unit tanpa evaluasi"),
    )
] + [
    ("Unemployment rate", "Tingkat pengangguran", MAKRO, KONTEKS, "Persen, kondisi makro"),
    ("Inflation rate", "Tingkat inflasi", MAKRO, KONTEKS, "Persen, kondisi makro"),
    ("GDP", "Produk domestik bruto (PDB)", MAKRO, KONTEKS, "Kondisi makro"),
]

BINARY = {"Displaced", "Educational special needs", "Debtor", "Tuition fees up to date",
          "Scholarship holder", "International"}

# Kalimat penjelasan faktor. Placeholder hanya merujuk fitur yang sama.
TEMPLATES = {
    "Debtor": {"naik": "Tercatat memiliki tunggakan biaya kuliah",
               "turun": "Tidak memiliki tunggakan biaya kuliah"},
    "Tuition fees up to date": {"naik": "Biaya kuliah belum lunas tepat waktu",
                                "turun": "Biaya kuliah lunas tepat waktu"},
    "Scholarship holder": {"naik": "Tidak menerima beasiswa",
                           "turun": "Menerima beasiswa"},
    "Displaced": {"naik": "Mahasiswa perantau, jauh dari daerah asal",
                  "turun": "Tinggal di daerah asal"},
    "Application order": {"naik": "Program studi ini pilihan ke-{urutan} saat pendaftaran",
                          "turun": "Program studi ini pilihan ke-{urutan} saat pendaftaran"},
    "Age at enrollment": {"naik": "Mulai kuliah pada usia {usia} tahun",
                          "turun": "Mulai kuliah pada usia {usia} tahun"},
    "Daytime/evening attendance": {"naik": "Kuliah di kelas malam",
                                   "turun": "Kuliah di kelas siang"},
    "Curricular units 1st sem (approved)": {"naik": "Hanya {lulus} dari {diambil} mata kuliah semester 1 yang lulus",
                                            "turun": "{lulus} dari {diambil} mata kuliah semester 1 berhasil lulus"},
    "Curricular units 2nd sem (approved)": {"naik": "Hanya {lulus} dari {diambil} mata kuliah semester 2 yang lulus",
                                            "turun": "{lulus} dari {diambil} mata kuliah semester 2 berhasil lulus"},
    "Curricular units 1st sem (grade)": {"naik": "Nilai rata-rata semester 1 hanya {nilai} dari skala 0–20",
                                         "turun": "Nilai rata-rata semester 1 mencapai {nilai} dari skala 0–20"},
    "Curricular units 2nd sem (grade)": {"naik": "Nilai rata-rata semester 2 hanya {nilai} dari skala 0–20",
                                         "turun": "Nilai rata-rata semester 2 mencapai {nilai} dari skala 0–20"},
    "Curricular units 2nd sem (without evaluations)": {"naik": "{tanpa} mata kuliah semester 2 tanpa evaluasi",
                                                       "turun": "Tidak ada mata kuliah semester 2 tanpa evaluasi"},
    "Curricular units 1st sem (without evaluations)": {"naik": "{tanpa} mata kuliah semester 1 tanpa evaluasi",
                                                       "turun": "Tidak ada mata kuliah semester 1 tanpa evaluasi"},
    "Curricular units 2nd sem (enrolled)": {"naik": "Hanya mengambil {diambil} mata kuliah pada semester 2",
                                            "turun": "Mengambil {diambil} mata kuliah pada semester 2"},
    "Curricular units 1st sem (enrolled)": {"naik": "Hanya mengambil {diambil} mata kuliah pada semester 1",
                                            "turun": "Mengambil {diambil} mata kuliah pada semester 1"},
}

TOKENS = {
    "urutan": "Application order",
    "usia": "Age at enrollment",
    "nilai": "self",
    "tanpa": "self",
}

# Fitur yang nilainya diberi konteks persentil data latih.
PERCENTILE = {
    "Curricular units 1st sem (approved)": "rendah",
    "Curricular units 2nd sem (approved)": "rendah",
    "Curricular units 1st sem (grade)": "rendah",
    "Curricular units 2nd sem (grade)": "rendah",
    "Admission grade": "rendah",
    "Age at enrollment": "tinggi",
}

UI_TERMS = {
    "Dropout": "Putus kuliah", "Enrolled": "Masih aktif", "Graduate": "Lulus",
    "probabilitas": "Peluang", "snapshot": "Tanggal pencatatan data",
    "shap": "Faktor yang paling mempengaruhi prediksi",
    "high": "Tinggi", "medium": "Sedang", "low": "Rendah",
}

HANDLING = ["Belum ditangani", "Dijadwalkan", "Sudah konseling", "Dipantau", "Penanganan selesai"]


def build():
    codes = json.loads((BACKEND / "category_labels.json").read_text())
    features = {}
    for name, label, group, factor, help_text in FEATURES:
        sem = "1st" if "1st sem" in name else "2nd" if "2nd sem" in name else None
        entry = {"label": label, "group": group, "factor_type": factor, "help": help_text}
        if name in BINARY:
            entry["values"] = {"0": "Tidak", "1": "Ya"}
        elif name == "Gender":
            entry["values"] = {"0": "Perempuan", "1": "Laki-laki"}
        elif name == "Daytime/evening attendance":
            entry["values"] = {"0": "Malam", "1": "Siang"}
        elif name == "Marital status":
            entry["values"] = {"1": "Lajang", "2": "Menikah", "3": "Duda/janda (ditinggal wafat)",
                               "4": "Bercerai", "5": "Hidup bersama (facto union)", "6": "Berpisah secara hukum"}
        elif name in codes:
            entry["values"] = {str(x["value"]): x["label"] for x in codes[name]}
        if name in TEMPLATES:
            entry["template"] = TEMPLATES[name]
            if sem:
                entry["template_tokens"] = {
                    "diambil": f"Curricular units {sem} sem (enrolled)",
                    "lulus": f"Curricular units {sem} sem (approved)"}
        if name in PERCENTILE:
            entry["percentile"] = PERCENTILE[name]
        features[name] = entry
    return {"version": "1.0", "features": features, "tokens": TOKENS,
            "ui_terms": UI_TERMS, "handling_statuses": HANDLING,
            "groups": [DEMOGRAFI, BIAYA, AKADEMIK, MAKRO],
            "factor_types": {"dapat_ditindaklanjuti": "Dapat ditindaklanjuti",
                             "konteks": "Konteks", "sensitif": "Sensitif"}}


if __name__ == "__main__":
    data = build()
    (BACKEND / "dictionary.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"{len(data['features'])} fitur → backend/dictionary.json")
