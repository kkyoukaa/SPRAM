"""Cache jawaban LLM: pertanyaan serupa memakai jawaban yang sama, tanpa panggilan baru.

Kunci cache = sidik pertanyaan yang dinormalkan + sidik konteks. Konteks
mengubah jawaban, jadi mahasiswa berbeda tidak pernah berbagi jawaban.
"""
import hashlib
import json
import re

# Sinonim sering dipakai dosen; dinormalkan sebelum sidik dihitung.
SINONIM = {
    'kenapa': 'mengapa', 'knp': 'mengapa', 'napa': 'mengapa',
    'gimana': 'bagaimana', 'gmn': 'bagaimana', 'bgmn': 'bagaimana',
    'langkah': 'tindakan', 'saran': 'tindakan', 'solusi': 'tindakan',
    'tindak': 'tindakan', 'penanganan': 'tindakan', 'atasi': 'tindakan',
    'mhs': 'mahasiswa', 'maba': 'mahasiswa',
    'risiko': 'risiko', 'resiko': 'risiko',
    'bayar': 'pembayaran', 'tunggakan': 'pembayaran', 'tagihan': 'pembayaran',
    'nilai': 'akademik', 'ipk': 'akademik', 'sks': 'akademik',
}

STOPWORD = {'yang', 'itu', 'ini', 'sih', 'dong', 'ya', 'kah', 'deh', 'nya',
            'apa', 'apakah', 'adalah', 'untuk', 'saya', 'aku', 'kami', 'kita',
            'mahasiswa', 'mhs', 'ini', 'nya', 'dan', 'atau', 'dengan', 'di', 'ke'}


def normalisasi(teks):
    t = re.sub(r'[^a-z0-9\s]', ' ', str(teks or '').lower())
    hasil = []
    for kata in t.split():
        kata = SINONIM.get(kata, kata)
        # "berisiko"/"merisaukan" -> "risiko"; "penanganan" -> "tindakan"
        if kata.startswith('ber') or kata.startswith('me'):
            akar = kata[3:] if kata.startswith('ber') else kata[2:]
            for calon in (akar, 'r' + akar):
                if calon in SINONIM or calon == 'risiko':
                    kata = SINONIM.get(calon, calon)
                    break
        if kata not in STOPWORD:
            hasil.append(kata)
    return ' '.join(sorted(set(hasil)))


def kunci(pertanyaan, konteks, versi='v2', scope=None):
    """Sidik cache. Batasan percakapan ikut dihitung: ubah aturan -> cache lama tidak dipakai."""
    bahan = '|'.join([versi, normalisasi(pertanyaan), sidik_konteks(konteks),
                      hashlib.sha256(json.dumps(scope or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]])
    return hashlib.sha256(bahan.encode()).hexdigest()[:32]


def sidik_konteks(konteks):
    """Konteks ringkas yang mempengaruhi jawaban: tingkat risiko + topik sinyal."""
    risiko = konteks.get('risiko') or {}
    topik = [r.get('topik', '') for r in (konteks.get('rekomendasi') or [])[:3]]
    faktor = sorted(f.get('nama', '') for f in (konteks.get('faktor') or [])[:3])
    bahan = '|'.join([str(risiko.get('tingkat')), ','.join(topik), ','.join(faktor)])
    return hashlib.sha256(bahan.encode()).hexdigest()[:16]
