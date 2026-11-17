"""Penerjemah tunggal: nama fitur, nilai kode, dan kalimat penjelasan faktor.

Semua halaman memakai modul ini agar istilah konsisten. Tidak ada fitur model
yang ditambah di sini — hanya membaca 36 fitur dataset.
"""
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parents[1]
DICTIONARY = Path(__file__).with_name("dictionary.json")
DISTRIBUTION = ROOT / "data" / "train_distribution.json"


@lru_cache(maxsize=1)
def kamus():
    return json.loads(DICTIONARY.read_text())


@lru_cache(maxsize=1)
def distribusi():
    return json.loads(DISTRIBUTION.read_text()) if DISTRIBUTION.exists() else {}


def fitur(nama):
    return kamus()["features"].get(nama, {})


def label(nama):
    return fitur(nama).get("label", nama)


def kelompok(nama):
    return fitur(nama).get("group", "Lainnya")


def jenis_faktor(nama):
    return fitur(nama).get("factor_type", "konteks")


def terjemahkan(nama, nilai):
    """Nilai kode → teks Indonesia. Kode tak terdaftar tidak pernah error."""
    entry = fitur(nama)
    if nilai is None or nilai == "":
        return "—"
    teks = str(nilai).strip()
    if teks.endswith(".0"):
        teks = teks[:-2]
    values = entry.get("values")
    if values:
        if teks in values:
            return values[teks]
        try:
            kunci = str(int(float(teks)))
            if kunci in values:
                return values[kunci]
        except (TypeError, ValueError):
            pass
        return f"Kode {teks} (belum terdaftar)"
    angka = float(teks) if teks.replace("-", "").replace(".", "").isdigit() else None
    if angka is None:
        return teks
    return str(int(angka)) if angka == int(angka) else f"{angka:g}"


def persentil(nama, nilai):
    """Pangkat persentil nilai terhadap distribusi data latih (0-100)."""
    data = distribusi().get(nama)
    if not data:
        return None
    try:
        nilai = float(nilai)
    except (TypeError, ValueError):
        return None
    bawah = sum(1 for x in data if x < nilai)
    return round(100 * bawah / len(data))


def kalimat(nama, nilai, arah, semua_nilai):
    """Kalimat faktor dari template kamus; fallback generik bila tak ada template."""
    entry = fitur(nama)
    teks_nilai = terjemahkan(nama, nilai)
    template = (entry.get("template") or {}).get(arah)
    pembagi = (entry.get("template_tokens") or {}).get("diambil")
    if template and pembagi and float(semua_nilai.get(pembagi) or 0) == 0:
        # Tanpa unit diambil, template "x dari 0" menyesatkan → pakai kalimat netral.
        return f"{label(nama)}: {teks_nilai} (tidak ada unit diambil pada semester tersebut)"
    if template:
        isi = {}
        for token, sumber in (entry.get("template_tokens") or {}).items():
            isi[token] = terjemahkan(sumber, semua_nilai.get(sumber))
        for token, sumber in kamus()["tokens"].items():
            if token in isi:
                continue
            isi[token] = teks_nilai if sumber == "self" else terjemahkan(sumber, semua_nilai.get(sumber))
        try:
            hasil = template.format(**isi)
        except (KeyError, IndexError):
            hasil = f"{label(nama)}: {teks_nilai}"
    else:
        hasil = f"{label(nama)}: {teks_nilai}"
    catatan = persentil(nama, nilai)
    if catatan is not None and entry.get("percentile") == "rendah" and catatan <= 40:
        hasil += f" — lebih rendah dari {100 - catatan}% mahasiswa lain"
    elif catatan is not None and entry.get("percentile") == "tinggi" and catatan >= 60:
        hasil += f" — lebih tinggi dari {catatan}% mahasiswa lain"
    return hasil


def label_kelas(kelas):
    return kamus()["ui_terms"].get(kelas, kelas)


def profil(features, tandai=()):
    """36 fitur → daftar terkelompok, siap tampil di Detail Mahasiswa."""
    urutan = kamus()["groups"]
    butir = []
    for nama, nilai in features.items():
        butir.append({
            "feature": nama, "label": label(nama), "value": nilai,
            "value_label": terjemahkan(nama, nilai), "group": kelompok(nama),
            "factor_type": jenis_faktor(nama), "help": fitur(nama).get("help", ""),
            "highlight": nama in tandai,
        })
    return sorted(butir, key=lambda x: (urutan.index(x["group"]) if x["group"] in urutan else 99,
                                        list(features).index(x["feature"])))
