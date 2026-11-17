"""Chat dikunci ke lingkup SPRAM: tanpa JSON, nama model, URL, atau kunci."""
import json
import re

from backend.advisor_chat import _ringkas, _sanitasi, answer, build_context

RAHASIA = 'sk-rahasiapanjang1234567890'


def sample():
    return {"student_id": "NIM-SECRET-1", "features": json.dumps({
        "Debtor": 1, "Gender": 1, "Tuition fees up to date": 0}),
        "probabilities": json.dumps({"Dropout": .81, "Enrolled": .12, "Graduate": .07}),
        "drivers": json.dumps([{"feature": "Debtor", "shap": .3}]),
        "risk_band": "high"}


def rule():
    return {"rule_id": "R01", "nama": "Indikasi kendala finansial",
            "hipotesis": "Kemungkinan tunggakan biaya",
            "pertanyaan": "Apakah ada kesulitan membayar biaya kuliah?",
            "alasan": ["Memiliki tunggakan = Ya"],
            "tindakan": {"belum_tahu": ["Tanyakan kondisi pembayaran"],
                         "ya": ["Rujuk ke bagian keuangan"],
                         "tidak": ["Pantau pembayaran"]}}


def test_konteks_berupa_kalimat_bukan_json():
    teks = _ringkas(build_context(sample(), [rule()]))
    assert not re.search(r'[{}\[\]]', teks), teks
    assert 'risiko' not in teks.lower() or 'peluang putus kuliah' in teks
    assert 'Debtor' not in teks
    assert '81 persen' in teks
    assert 'tingkat tinggi' in teks
    assert 'Apakah ada kesulitan membayar' in teks


def test_tidak_ada_nama_model_atau_url_ke_llm():
    terlihat = []
    answer('Apa langkah saya?', [], build_context(sample(), [rule()]),
           llm=lambda m: terlihat.extend(m) or 'Verifikasi pembayaran dulu.')
    dikirim = json.dumps(terlihat)
    assert not re.search(r'deepseek|qwen|claude|gpt|openai|anthropic', dikirim, re.I)
    assert 'http' not in dikirim
    assert 'sk-' not in dikirim


def test_output_json_dan_teknis_dibuang():
    bocor = ('Saran: cek pembayaran.\n'
             '{"fitur":{"Debtor":1,"probabilities":{}}}\n'
             f'Gunakan api_key {RAHASIA} ke https://10.1.1.1/v1 dengan model deepseek-v4.1-flash.')
    hasil = _sanitasi(bocor)
    assert 'Saran: cek pembayaran.' in hasil
    assert '{' not in hasil and '}' not in hasil
    assert RAHASIA not in hasil
    assert 'https' not in hasil
    assert not re.search(r'deepseek|api_key', hasil, re.I)


def test_jawaban_model_yang_bocor_diganti_mode_terbatas_atau_disaring():
    hasil = answer('Apa langkah saya?', [], build_context(sample(), [rule()]),
                   llm=lambda m: '{"probabilities":{"Dropout":0.81}} sk-abcdefgh12345678')
    assert hasil['mode'] == 'terbatas'
    assert 'probabilities' not in hasil['answer']
    assert 'sk-abcdefgh' not in hasil['answer']


def test_jawaban_wajar_tetap_utuh():
    asli = 'Data mencatat tunggakan, tetapi itu belum tentu penyebab. Minta bukti bayar lalu cocokkan ke bagian keuangan.'
    hasil = answer('Apa langkah saya?', [], build_context(sample(), [rule()]), llm=lambda m: asli)
    assert hasil['mode'] == 'ai'
    assert hasil['answer'] == asli
