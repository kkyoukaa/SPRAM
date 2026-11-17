"""Sistem pakar SPRAM: basis aturan + mesin inferensi forward chaining.

Modul murni (tanpa UI, tanpa database) agar bisa diuji sendiri. Kondisi aturan
hanya membaca 36 fitur dataset dan arah faktor (SHAP). Fitur sensitif dan fitur
makro ditolak sebagai kondisi aturan.
"""
import json
from pathlib import Path

from .dictionary import jenis_faktor, label, terjemahkan

ROOT = Path(__file__).parents[1]
THRESHOLDS_FILE = ROOT / "data" / "rule_thresholds.json"

FITUR_MAKRO = {"Unemployment rate", "Inflation rate", "GDP"}
JAWABAN = ("ya", "tidak", "belum_tahu")

PAGAR_AMAN = ("Bila jawaban mengarah ke kondisi psikologis, keluarga, atau kesehatan, "
              "arahkan mahasiswa ke layanan konseling profesional. Sistem tidak memberi "
              "saran lanjutan untuk topik tersebut.")

# Aturan awal (R01-R08). Disimpan ke tabel `rules` saat bootstrap, lalu dapat
# diubah admin lewat halaman Aturan.
DEFAULT_RULES = [
    {
        "rule_id": "R01", "nama": "Indikasi kendala finansial", "prioritas": 1, "topik": "finansial",
        "kondisi": [{"fitur": "Debtor", "op": "==", "nilai": 1}],
        "kondisi_atau": [[{"fitur": "Tuition fees up to date", "op": "==", "nilai": 0}]],
        "hipotesis": "Kemungkinan mahasiswa mengalami kendala finansial.",
        "pertanyaan": "Apakah ada kesulitan membayar biaya kuliah semester ini?",
        "tindakan": {"ya": ["Rujuk ke bagian keuangan/kemahasiswaan", "Informasikan keringanan atau beasiswa"],
                     "tidak": ["Pantau status pembayaran semester berikutnya"],
                     "belum_tahu": ["Jadwalkan percakapan untuk menggali kondisi finansial"]},
    },
    {
        "rule_id": "R02", "nama": "Kesulitan akademik", "prioritas": 2, "topik": "akademik",
        "kondisi_atau": [
            [{"rasio": ["Curricular units 1st sem (approved)", "Curricular units 1st sem (enrolled)"],
              "op": "<=", "nilai_from": "approval_ratio_p25"}],
            [{"rasio": ["Curricular units 2nd sem (approved)", "Curricular units 2nd sem (enrolled)"],
              "op": "<=", "nilai_from": "approval_ratio_p25"}],
            [{"selisih": ["Curricular units 2nd sem (grade)", "Curricular units 1st sem (grade)"],
              "op": "<=", "nilai_from": "grade_drop_p25"}],
        ],
        "hipotesis": "Kemungkinan mahasiswa mengalami kesulitan akademik.",
        "pertanyaan": "Apakah mahasiswa menyampaikan kesulitan mengikuti materi atau ujian?",
        "tindakan": {"ya": ["Bimbingan akademik terjadwal", "Arahkan ke tutor sebaya atau kelas remedial"],
                     "tidak": ["Tinjau beban studi dan strategi belajar bersama mahasiswa"],
                     "belum_tahu": ["Minta bukti tugas/evaluasi terakhir untuk ditinjau bersama"]},
    },
    {
        "rule_id": "R03", "nama": "Kemungkinan bekerja sambil kuliah", "prioritas": 3, "topik": "beban",
        "kondisi": [{"fitur": "Daytime/evening attendance", "op": "==", "nilai": 0},
                    {"fitur": "Age at enrollment", "op": ">=", "nilai_from": "age_p75"}],
        "hipotesis": "Kemungkinan mahasiswa bekerja sambil kuliah.",
        "pertanyaan": "Apakah mahasiswa memiliki pekerjaan tetap di samping kuliah?",
        "tindakan": {"ya": ["Diskusikan pengaturan beban studi", "Tawarkan jadwal konsultasi di luar jam kerja"],
                     "tidak": ["Konfirmasi alasan pilihan kelas malam"],
                     "belum_tahu": ["Tanyakan pola waktu kuliah dan kerja pada pertemuan berikutnya"]},
    },
    {
        "rule_id": "R04", "nama": "Kurang minat / kurang cocok dengan program studi", "prioritas": 4, "topik": "minat",
        "kondisi": [{"fitur": "Application order", "op": ">=", "nilai_from": "application_order_p90"}],
        "hipotesis": "Kemungkinan program studi bukan pilihan utama mahasiswa.",
        "pertanyaan": "Apakah mahasiswa menyampaikan keraguan terhadap program studi yang dijalani?",
        "tindakan": {"ya": ["Konseling minat dan karier", "Informasikan opsi pindah program sesuai aturan akademik"],
                     "tidak": ["Pantau motivasi pada pertemuan berikutnya"],
                     "belum_tahu": ["Ajak mahasiswa memetakan minat dan tujuan studi"]},
    },
    {
        "rule_id": "R05", "nama": "Adaptasi dan biaya hidup perantau", "prioritas": 5, "topik": "adaptasi",
        "kondisi": [{"fitur": "Displaced", "op": "==", "nilai": 1}],
        "hipotesis": "Kemungkinan mahasiswa menghadapi kendala adaptasi atau biaya hidup sebagai perantau.",
        "pertanyaan": "Apakah mahasiswa mengalami kendala tempat tinggal atau adaptasi di kota studi?",
        "tindakan": {"ya": ["Informasikan tempat tinggal, komunitas, dan dukungan sebaya", "Hubungkan dengan layanan kemahasiswaan"],
                     "tidak": ["Tetap tawarkan dukungan komunitas mahasiswa"],
                     "belum_tahu": ["Tanyakan kondisi tempat tinggal pada pertemuan berikutnya"]},
    },
    {
        "rule_id": "R06", "nama": "Belum ada dukungan finansial", "prioritas": 6, "topik": "finansial",
        "kondisi": [{"fitur": "Scholarship holder", "op": "==", "nilai": 0},
                    {"aturan_aktif": "R01"}],
        "hipotesis": "Kemungkinan mahasiswa belum menerima dukungan beasiswa.",
        "pertanyaan": "Apakah mahasiswa sudah mengetahui skema beasiswa yang tersedia?",
        "tindakan": {"ya": ["Bantu proses pengajuan beasiswa yang relevan"],
                     "tidak": ["Informasikan skema beasiswa dan tenggat pendaftaran"],
                     "belum_tahu": ["Kirim ringkasan skema beasiswa kepada mahasiswa"]},
    },
    {
        "rule_id": "R07", "nama": "Tidak mengikuti ujian atau perkuliahan", "prioritas": 7, "topik": "kehadiran",
        "kondisi_atau": [
            [{"rasio": ["Curricular units 1st sem (evaluations)", "Curricular units 1st sem (enrolled)"],
              "op": "<=", "nilai_from": "evaluation_ratio_p25", "batas_atas": 0.99}],
            [{"rasio": ["Curricular units 2nd sem (evaluations)", "Curricular units 2nd sem (enrolled)"],
              "op": "<=", "nilai_from": "evaluation_ratio_p25", "batas_atas": 0.99}],
            [{"fitur": "Curricular units 1st sem (without evaluations)", "op": ">=", "nilai_from": "without_evaluations_p75", "nilai_min": 1}],
            [{"fitur": "Curricular units 2nd sem (without evaluations)", "op": ">=", "nilai_from": "without_evaluations_p75", "nilai_min": 1}],
        ],
        "hipotesis": "Kemungkinan mahasiswa tidak mengikuti sebagian evaluasi atau perkuliahan.",
        "pertanyaan": "Apakah mahasiswa absen atau tidak mengikuti ujian tertentu?",
        "tindakan": {"ya": ["Hubungi mahasiswa segera", "Cek kehadiran dan kendalanya bersama bagian akademik"],
                     "tidak": ["Pastikan status evaluasi sudah tercatat benar"],
                     "belum_tahu": ["Minta rekap kehadiran dan evaluasi terakhir"]},
    },
    {
        "rule_id": "R08", "nama": "Penyebab belum teridentifikasi", "prioritas": 8, "topik": "umum",
        "fallback": True,
        "kondisi": [{"risiko": "high"}],
        "hipotesis": "Risiko tinggi tanpa sinyal aturan lain yang cocok.",
        "pertanyaan": "Apakah ada kondisi lain yang belum tercatat dan perlu didiskusikan?",
        "tindakan": {"ya": ["Lakukan percakapan terstruktur dengan mahasiswa", "Catat temuan pada tindak lanjut"],
                     "tidak": ["Lakukan percakapan terstruktur umum untuk memetakan kondisi"],
                     "belum_tahu": ["Jadwalkan percakapan terstruktur dengan mahasiswa"]},
    },
]

OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, ">": lambda a, b: a > b,
       ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}


def thresholds():
    return json.loads(THRESHOLDS_FILE.read_text())


def _nilai(item, ambang):
    if "nilai_from" in item:
        nilai = ambang.get(item["nilai_from"])
        if nilai is None:
            raise KeyError(item["nilai_from"])
    else:
        nilai = item["nilai"]
    if "batas_atas" in item:
        nilai = min(nilai, item["batas_atas"])
    if "nilai_min" in item:
        nilai = max(nilai, item["nilai_min"])
    return nilai


def _fitur_rule(rule):
    items = list(rule.get("kondisi") or [])
    for grup in rule.get("kondisi_atau") or []:
        items.extend(grup)
    return {i["fitur"] for i in items if i.get("fitur")}


def validasi_rule(rule, fitur_valid):
    """Tolak fitur sensitif/makro dan nama fitur di luar 36 fitur model."""
    galat = []
    for nama in sorted(_fitur_rule(rule)):
        if nama not in fitur_valid:
            galat.append(f"{nama} bukan bagian dari 36 fitur model")
        elif jenis_faktor(nama) == "sensitif":
            galat.append(f"{nama} adalah fitur sensitif dan tidak boleh menjadi kondisi aturan")
        elif nama in FITUR_MAKRO:
            galat.append(f"{nama} adalah fitur makro dan tidak boleh menjadi kondisi aturan")
    if not rule.get("pertanyaan") or not rule.get("hipotesis"):
        galat.append("Hipotesis dan pertanyaan wajib diisi")
    return galat


def _uji(item, fitur, drivers, ambang):
    if "shap_arah" in item:
        arah = "increase" if item["shap_arah"] == "naik_risiko" else "decrease"
        target = item.get("fitur")
        cocok = [d for d in drivers if d.get("direction") == arah and (not target or d["feature"] == target)]
        if not cocok:
            return False
        return True
    if "aturan_aktif" in item:
        return False  # diisi oleh pemanggil
    if "risiko" in item:
        return False  # diisi oleh pemanggil
    try:
        if "rasio" in item:
            a, b = item["rasio"]
            pembagi = float(fitur.get(b) or 0)
            if pembagi <= 0:
                return False
            kiri = float(fitur.get(a) or 0) / pembagi
        elif "selisih" in item:
            a, b = item["selisih"]
            kiri = float(fitur.get(a) or 0) - float(fitur.get(b) or 0)
        else:
            kiri = float(fitur.get(item["fitur"]) or 0)
        return OPS[item.get("op", "==")](kiri, float(_nilai(item, ambang)))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def _alasan(item, fitur, ambang):
    if "shap_arah" in item:
        arah = "menaikkan" if item["shap_arah"] == "naik_risiko" else "menurunkan"
        nama = item.get("fitur")
        return (f"faktor {label(nama)} {arah} risiko" if nama
                else f"terdapat faktor yang {arah} risiko")
    if "aturan_aktif" in item:
        return f"aturan {item['aturan_aktif']} aktif"
    if "risiko" in item:
        return f"risiko model tergolong {item['risiko']}"
    if "rasio" in item:
        a, b = item["rasio"]
        pembagi = float(fitur.get(b) or 0)
        rasio = (float(fitur.get(a) or 0) / pembagi) if pembagi else 0
        return (f"{terjemahkan(a, fitur.get(a))} {label(a).split(':', 1)[-1].strip()} "
                f"dari {terjemahkan(b, fitur.get(b))} {label(b).split(':', 1)[-1].strip()} "
                f"(rasio {rasio:.2f}, ambang {_nilai(item, ambang):g})")
    if "selisih" in item:
        a, b = item["selisih"]
        return (f"nilai {label(a).split(':', 1)[-1].strip()} turun dari semester sebelumnya "
                f"(ambang {_nilai(item, ambang):g})")
    nama = item["fitur"]
    return f"{label(nama)} = {terjemahkan(nama, fitur.get(nama))}"


def _cek(item, fitur, drivers, ambang, aktif_ids, risk_band):
    if "aturan_aktif" in item:
        return item["aturan_aktif"] in aktif_ids
    if "risiko" in item:
        return risk_band == item["risiko"]
    return _uji(item, fitur, drivers, ambang)


def evaluasi(rule, fitur, drivers, ambang, aktif_ids=(), risk_band=None):
    """True bila seluruh kondisi aturan terpenuhi, beserta alasannya."""
    kondisi = rule.get("kondisi") or []
    if isinstance(kondisi, dict):
        kondisi = kondisi.get("dan", [])
    # ponytail: R01 lama tersimpan sebagai kondisi DAN + opsi, padahal maksudnya ATAU.
    # Ubah format tersimpan lewat migrasi bila skema aturan diperluas.
    if rule.get("rule_id") == "R01" and rule.get("kondisi_atau"):
        groups = [kondisi] + rule["kondisi_atau"]
        for group in groups:
            if group and all(_cek(i, fitur, drivers, ambang, aktif_ids, risk_band) for i in group):
                return True, [_alasan(i, fitur, ambang) for i in group]
        return False, []
    alasan = []
    ok = True
    for item in kondisi:
        if not _cek(item, fitur, drivers, ambang, aktif_ids, risk_band):
            ok = False
            break
        alasan.append(_alasan(item, fitur, ambang))
    if ok and rule.get("kondisi_atau"):
        ok = False
        for grup in rule["kondisi_atau"]:
            grup_alasan = [_alasan(i, fitur, ambang) for i in grup
                           if _cek(i, fitur, drivers, ambang, aktif_ids, risk_band)]
            if len(grup_alasan) == len(grup):
                ok = True
                alasan.extend(grup_alasan)
                break
    return ok, alasan


def aturan_aktif(fitur, drivers, risk_band, rules, ambang=None):
    ambang = ambang or thresholds()
    aktif, ids = [], set()
    fallback = []
    for rule in sorted(rules, key=lambda r: r.get("prioritas", 99)):
        if not rule.get("aktif", 1):
            continue
        if rule.get("fallback"):
            fallback.append(rule)
            continue
        ok, alasan = evaluasi(rule, fitur, drivers, ambang, ids, risk_band)
        if ok:
            ids.add(rule["rule_id"])
            aktif.append({**rule, "alasan": alasan})
    if not aktif:
        for rule in fallback:
            ok, alasan = evaluasi(rule, fitur, drivers, ambang, ids, risk_band)
            if ok:
                ids.add(rule["rule_id"])
                aktif.append({**rule, "alasan": alasan})
    return aktif


def kontribusi(rule, drivers):
    fitur = _fitur_rule(rule)
    return max([abs(d.get("shap", 0)) for d in drivers if d["feature"] in fitur] or [0])


def rekomendasi(aktif, jawaban, risk_band, drivers=()):
    """Forward chaining: jawaban dosen menambah fakta, bukan mengubah model."""
    hasil = []
    for rule in sorted(aktif, key=lambda r: (r.get("prioritas", 99), -kontribusi(r, drivers))):
        jawab = (jawaban or {}).get(rule["rule_id"])
        tindakan = (rule.get("tindakan") or {}).get(jawab or "belum_tahu", [])
        hasil.append({
            "rule_id": rule["rule_id"], "nama": rule["nama"], "prioritas": rule.get("prioritas", 99),
            "hipotesis": rule["hipotesis"], "pertanyaan": rule["pertanyaan"],
            "jawaban": jawab, "tindakan": tindakan, "alasan": rule.get("alasan", []),
            "topik": rule.get("topik", "umum"),
        })
    pagar = any(r.get("topik") in ("umum", "kesehatan", "keluarga", "psikologis") for r in aktif)
    return {"rekomendasi": hasil, "pagar_aman": PAGAR_AMAN if pagar else None,
            "risiko": risk_band}
