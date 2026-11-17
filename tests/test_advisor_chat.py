"""Chat dosen: rekomendasi berpijak fakta, LLM opsional, fallback jujur."""
import json

from backend.advisor_chat import build_context, answer, call_model
from unittest.mock import patch
import io
import os
import urllib.request


def test_local_model_without_api_key():
    seen = {}
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    def fake(request, timeout):
        seen['url'] = request.full_url
        seen['headers'] = dict(request.header_items())
        seen['payload'] = json.loads(request.data)
        seen['timeout'] = timeout
        return Response(json.dumps({'choices': [{'message': {'content': 'Mari cek datanya bersama.'}}]}).encode())
    env = {'SPRAM_LLM_API_KEY': 'dummy-key-for-test'}
    with patch.dict(os.environ, env, clear=True), patch.object(urllib.request, 'urlopen', fake):
        assert call_model([{'role': 'user', 'content': 'Apa langkah berikutnya?'}]) == 'Mari cek datanya bersama.'
    assert seen['url'] == 'http://10.168.20.228:20128/v1/chat/completions'
    assert seen['headers'].get('Authorization') == 'Bearer dummy-key-for-test'
    assert seen['payload']['model'] == 'in/cb/deepseek-v4.1-flash'
    assert seen['payload']['stream'] is False
    assert seen['timeout'] == 25


def test_missing_key_raises_not_silent():
    with patch.dict(os.environ, {}, clear=True):
        try:
            call_model([{'role': 'user', 'content': 'x'}])
        except ValueError as e:
            assert 'belum ada model aktif' in str(e).lower()
        else:
            assert False, 'tanpa API key harus gagal, bukan diam'


def test_model_error_is_not_treated_as_answer():
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    env = {'SPRAM_LLM_API_KEY': 'dummy'}
    with patch.dict(os.environ, env, clear=True), patch.object(urllib.request, 'urlopen', return_value=Response(b'{"error":"model missing"}')):
        try:
            call_model([{'role': 'user', 'content': 'Apa langkah berikutnya?'}])
        except (ValueError, KeyError):
            pass
        else:
            assert False, 'error gateway tidak boleh dianggap jawaban'



def sample():
    return {"student_id": "NIM-SECRET-123", "probabilities": json.dumps({"Dropout": .72, "Enrolled": .18, "Graduate": .10}),
            "risk_band": "high", "features": json.dumps({"Debtor": 1, "Gender": 1, "Age at enrollment": 22}),
            "drivers": json.dumps([{"feature": "Debtor", "shap": .22}, {"feature": "Gender", "shap": .1}])}


def rule():
    return {"rule_id": "R01", "nama": "Indikasi kendala finansial",
            "hipotesis": "Kemungkinan ada kendala biaya.", "pertanyaan": "Apakah ada kesulitan membayar biaya kuliah?",
            "alasan": ["Memiliki tunggakan = Ya"],
            "tindakan": {"ya": ["Rujuk ke bagian keuangan"],
                         "tidak": ["Pantau pembayaran berikutnya"],
                         "belum_tahu": ["Tanyakan kondisi pembayaran kepada mahasiswa"]}}


def test_context_only_actionable_facts_and_conditional_recommendation():
    ctx = build_context(sample(), [rule()])
    text = json.dumps(ctx, ensure_ascii=False)
    assert "NIM-SECRET-123" not in text and "Gender" not in text
    assert "Laki-laki" not in text and "Perempuan" not in text
    assert "tunggakan" in text.lower()
    assert ctx["risiko"]["peluang_putus_kuliah"] == .72
    assert ctx["rekomendasi"][0]["verifikasi"] == "Apakah ada kesulitan membayar biaya kuliah?"
    assert ctx["rekomendasi"][0]["jika_ya"] == ["Rujuk ke bagian keuangan"]
    assert ctx["rekomendasi"][0]["jika_tidak"] == ["Pantau pembayaran berikutnya"]
    assert ctx["rekomendasi"][0]["sementara"] == ["Tanyakan kondisi pembayaran kepada mahasiswa"]


def test_unavailable_model_never_fakes_freeform_answer():
    result = answer("Apa jadwal beasiswa kampus minggu depan?", [], build_context(sample(), [rule()]),
                    llm=lambda messages: (_ for _ in ()).throw(TimeoutError()))
    assert result["mode"] == "terbatas"
    assert "tidak dapat memastikan" in result["answer"].lower()
    assert "jadwal" in result["answer"].lower()


def test_offline_recommendation_stays_conditional_and_specific():
    ctx = build_context(sample(), [rule()])
    result = answer("Apa langkah berikutnya?", [], ctx, llm=lambda messages: (_ for _ in ()).throw(TimeoutError()))
    assert result['mode'] == 'terbatas'
    assert 'tunggakan' in result['answer'].lower()
    assert 'Apakah ada kesulitan membayar biaya kuliah?' in result['answer']
    assert 'Tanyakan kondisi pembayaran kepada mahasiswa' in result['answer']
    assert 'Rujuk ke bagian keuangan' not in result['answer']


def test_unrelated_question_does_not_append_irrelevant_student_hypothesis():
    ctx = build_context(sample(), [rule()])
    result = answer('Kapan jadwal beasiswa kampus dibuka?', [], ctx, llm=lambda messages: (_ for _ in ()).throw(TimeoutError()))
    assert 'jadwal' in result['answer'].lower()
    assert 'cek sumber resmi' in result['answer'].lower()
    assert 'tunggakan' not in result['answer'].lower()


def test_context_hides_identity_even_in_free_text_history():
    seen = []
    answer('Bagaimana NIM-SECRET-123?', [{'role': 'user', 'content': 'NIM-SECRET-123'}],
           build_context(sample(), [rule()]), llm=lambda messages: seen.extend(messages) or 'Perlu verifikasi.')
    assert 'NIM-SECRET-123' not in json.dumps(seen)


def test_freeform_model_uses_conversation_and_no_identity():
    seen = []
    def fake(messages):
        seen.extend(messages)
        return "Kita cek dulu kondisi pembayaran, lalu tanyakan kesulitannya sebelum merujuk bagian keuangan."
    result = answer("Kalau ia sudah membayar, langkah berikutnya?",
                    [{"role": "user", "content": "Mahasiswa ini punya tunggakan?"},
                     {"role": "assistant", "content": "Datanya mencatat tunggakan."}],
                    build_context(sample(), [rule()]), llm=fake)
    assert result["mode"] == "ai" and "cek dulu" in result["answer"]
    joined = json.dumps(seen, ensure_ascii=False)
    assert "Kalau ia sudah membayar" in joined and "Datanya mencatat tunggakan" in joined
    assert "NIM-SECRET-123" not in joined and "Gender" not in joined


def test_invalid_model_output_falls_back():
    ctx = build_context(sample(), [rule()])
    for bad in ("", "   ", "\u200b"):
        result = answer("Apa langkahnya?", [], ctx, llm=lambda messages: bad)
        assert result["mode"] == "terbatas"


def test_question_and_history_bounded():
    ctx = build_context(sample(), [rule()])
    result = answer("x" * 2001, [], ctx, llm=lambda messages: "jawab")
    assert result["mode"] == "terbatas"
    seen = []
    history = [{"role": "user", "content": "rahasia"} for _ in range(30)]
    answer("Langkah?", history, ctx, llm=lambda messages: seen.extend(messages) or "Jawaban")
    assert len(seen) <= 8


def test_financial_rule_fires_on_debt_or_overdue_fees():
    from backend.expert import DEFAULT_RULES, aturan_aktif
    base = {'Debtor': 0, 'Tuition fees up to date': 1}
    for facts in ({'Debtor': 1}, {'Tuition fees up to date': 0}):
        active = aturan_aktif({**base, **facts}, [], 'medium', DEFAULT_RULES)
        assert 'R01' in [r['rule_id'] for r in active]
    active = aturan_aktif(base, [], 'medium', DEFAULT_RULES)
    assert 'R01' not in [r['rule_id'] for r in active]


def test_no_rules_means_no_invented_diagnosis():
    ctx = build_context(sample(), [])
    assert ctx["rekomendasi"] == []
    result = answer("Apa penyebab putus kuliah?", [], ctx, llm=lambda messages: "Belum bisa menyimpulkan penyebabnya.")
    assert result["mode"] == "ai"
    assert "penyebab" in result["answer"]
