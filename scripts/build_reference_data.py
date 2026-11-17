#!/usr/bin/env python3
"""Turunkan ambang aturan + distribusi persentil dari data latih.

Tidak menambah fitur dan tidak mengubah dataset: hanya membaca distribusi
data.csv lalu menyimpan hasilnya ke data/. Setiap ambang dicatat cara
penentuannya agar bisa dilaporkan.

    .venv/bin/python scripts/build_reference_data.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
DATASET = ROOT.parent / "data.csv"
OUT = ROOT / "data"

PERCENTILE_FEATURES = [
    "Curricular units 1st sem (approved)", "Curricular units 2nd sem (approved)",
    "Curricular units 1st sem (grade)", "Curricular units 2nd sem (grade)",
    "Admission grade", "Age at enrollment",
]

# Keterangan panel admin: nama awam, arti persentil, aturan pemakai, alasan pembatasan.
META = {
    "age_p75": {
        "judul": "Usia saat mendaftar", "satuan": "tahun",
        "arti": "75% mahasiswa data latih mendaftar pada usia 25 tahun atau kurang.",
        "dipakai": "R03 — kemungkinan bekerja sambil kuliah (kelas malam dan usia 25 tahun ke atas).",
    },
    "application_order_p90": {
        "judul": "Urutan pilihan program studi", "satuan": "pilihan ke-",
        "arti": "90% mahasiswa data latih mendaftar pada pilihan ke-1 sampai ke-3.",
        "dipakai": "R04 — kurang minat atau kurang cocok dengan program studi (pilihan ke-4 dan seterusnya).",
    },
    "approval_ratio_p25": {
        "judul": "Rasio mata kuliah lulus", "satuan": "bagian dari yang diambil",
        "arti": "25% mahasiswa data latih hanya lulus 43% atau kurang dari mata kuliah yang diambil (semester 1 dan 2 digabung).",
        "dipakai": "R02 — kesulitan akademik (rasio lulus 0,43 atau kurang).",
    },
    "evaluation_ratio_p25": {
        "judul": "Rasio evaluasi diikuti", "satuan": "bagian dari yang diambil",
        "arti": "Hampir semua mahasiswa data latih mengikuti seluruh evaluasi, sehingga persentil 25 mentok di 1,0.",
        "dipakai": "R07 — tidak mengikuti ujian atau perkuliahan.",
        "catatan": "Ambang dibatasi maksimal 0,99. Tanpa batas itu seluruh populasi ikut terkena aturan; yang dinilai bolos hanya mahasiswa yang mengikuti kurang dari 100% evaluasi.",
    },
    "without_evaluations_p75": {
        "judul": "Mata kuliah tanpa evaluasi", "satuan": "mata kuliah",
        "arti": "Mayoritas mahasiswa data latih bernilai 0, sehingga persentil 75 juga 0.",
        "dipakai": "R07 — tidak mengikuti ujian atau perkuliahan.",
        "catatan": "Ambang dinaikkan minimal 1 mata kuliah agar aturan punya arti.",
    },
    "grade_drop_p25": {
        "judul": "Perubahan nilai semester 2 dibanding semester 1", "satuan": "poin nilai",
        "arti": "25% mahasiswa data latih nilainya turun 0,6 poin atau lebih dari semester 1 ke semester 2.",
        "dipakai": "R02 — kesulitan akademik (nilai turun 0,6 poin atau lebih).",
    },
}


def main():
    frame = pd.read_csv(DATASET, sep=";")
    frame.columns = [c.strip().rstrip("\t") for c in frame.columns]
    OUT.mkdir(parents=True, exist_ok=True)

    distribusi = {f: sorted(round(float(v), 3) for v in frame[f]) for f in PERCENTILE_FEATURES}
    (OUT / "train_distribution.json").write_text(json.dumps(distribusi))

    enrolled1 = frame["Curricular units 1st sem (enrolled)"].clip(lower=1)
    enrolled2 = frame["Curricular units 2nd sem (enrolled)"].clip(lower=1)
    ratio = pd.concat([
        frame["Curricular units 1st sem (approved)"] / enrolled1,
        frame["Curricular units 2nd sem (approved)"] / enrolled2,
    ])
    eval_ratio = pd.concat([
        frame["Curricular units 1st sem (evaluations)"] / enrolled1,
        frame["Curricular units 2nd sem (evaluations)"] / enrolled2,
    ])
    tanpa = pd.concat([
        frame["Curricular units 1st sem (without evaluations)"],
        frame["Curricular units 2nd sem (without evaluations)"],
    ])
    delta = frame["Curricular units 2nd sem (grade)"] - frame["Curricular units 1st sem (grade)"]

    ambang = {
        "version": "rule-v1",
        "dataset_rows": int(len(frame)),
        "age_p75": round(float(frame["Age at enrollment"].quantile(.75)), 2),
        "application_order_p90": round(float(frame["Application order"].quantile(.90)), 2),
        "approval_ratio_p25": round(float(ratio.quantile(.25)), 4),
        "evaluation_ratio_p25": round(float(eval_ratio.quantile(.25)), 4),
        "without_evaluations_p75": round(float(tanpa.quantile(.75)), 2),
        "grade_drop_p25": round(float(delta.quantile(.25)), 2),
        "derivation": {
            "age_p75": "Persentil 75 usia saat mendaftar pada data latih",
            "application_order_p90": "Persentil 90 urutan pilihan pendaftaran pada data latih",
            "approval_ratio_p25": "Persentil 25 rasio unit lulus/unit diambil (sem 1 dan 2 digabung)",
            "evaluation_ratio_p25": "Persentil 25 rasio evaluasi diikuti/unit diambil. Karena mayoritas mahasiswa mengikuti semua evaluasi, aturan memakai batas min(persentil ini, 0,99) agar tidak menjangkau seluruh populasi",
            "without_evaluations_p75": "Persentil 75 jumlah unit tanpa evaluasi. Karena mayoritas bernilai 0, aturan memakai ambang minimal 1 unit",
            "grade_drop_p25": "Persentil 25 selisih nilai semester 2 dikurangi semester 1",
        },
        # Keterangan untuk panel admin (dipakai RulesAdmin.jsx). Ditulis manual karena
        # butuh nama aturan dan alasan pembatasan, bukan angka hasil hitung.
        "meta": META,
    }
    (OUT / "rule_thresholds.json").write_text(json.dumps(ambang, indent=1))
    print(json.dumps(ambang, indent=1))


if __name__ == "__main__":
    main()
