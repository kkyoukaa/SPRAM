#!/usr/bin/env python3
"""Pemeriksa kamus bahasa Indonesia (Fase 1.5 / 8.4).

Memastikan:
1. 36 fitur model punya label, kelompok, dan jenis faktor di kamus.
2. Setiap nilai unik pada data latih punya padanan teks Indonesia.
3. Tidak ada label yang masih memakai nama Inggris dataset.
4. Aturan di basis pengetahuan hanya memakai fitur yang sah.

    .venv/bin/python scripts/check_dictionary.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from backend.dictionary import kamus, terjemahkan  # noqa: E402
from backend.expert import validasi_rule  # noqa: E402
from backend.ml import UPDATE_FEATURES  # noqa: E402

DATA = ROOT.parent / "data.csv"


def main():
    masalah = []
    k = kamus()
    fitur = k["features"]

    hilang = [f for f in UPDATE_FEATURES if f not in fitur]
    if hilang:
        masalah.append(f"Fitur belum ada di kamus: {', '.join(hilang)}")
    ekstra = [f for f in fitur if f not in UPDATE_FEATURES]
    if ekstra:
        masalah.append(f"Kamus memuat fitur di luar model: {', '.join(ekstra)}")
    for nama, entry in fitur.items():
        if entry.get("label") in (None, "", nama):
            masalah.append(f"{nama}: label masih nama asli/kosong")
        if not entry.get("group"):
            masalah.append(f"{nama}: kelompok kosong")
        if entry.get("factor_type") not in ("dapat_ditindaklanjuti", "konteks", "sensitif"):
            masalah.append(f"{nama}: jenis faktor tidak sah")

    with DATA.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    kolom = {c.strip().rstrip("\t"): c for c in rows[0].keys()}
    for nama in UPDATE_FEATURES:
        if nama not in kolom:
            masalah.append(f"Kolom {nama} tidak ditemukan di data latih")
            continue
        nilai = {r[kolom[nama]].strip() for r in rows}
        for v in sorted(nilai):
            hasil = terjemahkan(nama, v)
            if hasil.startswith("Kode ") and hasil.endswith("(belum terdaftar)"):
                masalah.append(f"{nama}: nilai {v} belum punya teks Indonesia")

    if "rules" in k:
        pass
    aturan_file = ROOT / "data" / "spram.sqlite"
    if aturan_file.exists():
        import sqlite3

        with sqlite3.connect(aturan_file) as c:
            for row in c.execute("SELECT rule_id,nama,kondisi_json,hipotesis,pertanyaan,tindakan_json FROM rules WHERE aktif=1"):
                rid, nama, kondisi, hipotesis, pertanyaan, tindakan = row
                kk = json.loads(kondisi or "{}")
                galat = validasi_rule({"rule_id": rid, "nama": nama, "kondisi": kk.get("dan", []),
                                       "kondisi_atau": kk.get("atau", []), "hipotesis": hipotesis,
                                       "pertanyaan": pertanyaan, "tindakan": json.loads(tindakan or "{}")},
                                      set(UPDATE_FEATURES))
                masalah.extend(f"{rid}: {g}" for g in galat)

    if masalah:
        print("KAMUS BELUM LULUS")
        for m in masalah[:60]:
            print(f" - {m}")
        print(f"Total masalah: {len(masalah)}")
        return 1
    print(f"KAMUS LULUS: {len(fitur)} fitur, {len(rows)} baris data latih, semua nilai punya teks Indonesia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
