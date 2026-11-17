"""Batasan percakapan diatur admin di panel Aturan dan dipakai chatbot (sejalur)."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.advisor_chat import DEFAULT_SCOPE, _system_prompt
from backend.app import create_app

ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'BOOTSTRAP_MODELS': False,
                      'DATABASE': str(tmp_path / 'db.sqlite'),
                      'CREDENTIALS_FILE': str(tmp_path / 'creds.txt'),
                      'ARTIFACT_DIR': str(ROOT / 'artifacts'), 'SECRET_KEY': 'test'})
    with sqlite3.connect(app.config['DATABASE']) as db:
        db.execute("INSERT INTO predictions(id,student_id,stage,snapshot_date,features,probabilities,"
                   "predicted_class,risk_band,model_version,schema_version,drivers,protectors,"
                   "idempotency_key,created_at) VALUES('p1','STD-0001','academic_update','2026-10-01',"
                   "?,?,'Dropout','high','v1','v1',?,'[]',NULL,'2026-10-01')",
                   (json.dumps({'Debtor': 1}), json.dumps({'Dropout': .72, 'Enrolled': .2, 'Graduate': .08}),
                    json.dumps([{'feature': 'Debtor', 'shap': .22}])))
        db.execute("INSERT INTO assignments(advisor_id,student_id) VALUES(2,'STD-0001')")
    return app.test_client()


def login(client, email='admin@spram.local'):
    lines = Path(client.application.config['CREDENTIALS_FILE']).read_text().splitlines()
    pw = lines[next(i for i, l in enumerate(lines) if email in l) + 1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': email, 'password': pw},
                    headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json['csrf_token']}


def test_panel_aturan_menampilkan_batasan_default(client):
    h = login(client)
    d = client.get('/api/rules', headers=h).get_json()
    scope = d['chat_scope']
    assert scope['lingkup'] == DEFAULT_SCOPE['lingkup']
    assert scope['ditolak'] == DEFAULT_SCOPE['ditolak']
    assert scope['aktif'] is True


def test_admin_bisa_mengubah_batasan(client):
    h = login(client)
    r = client.put('/api/rules/chat-scope', headers=h, json={
        'lingkup': 'hanya jadwal konsultasi dan hasil studi',
        'ditolak': 'politik, agama, topik pribadi dosen',
        'nada': 'singkat, maksimal 2 kalimat',
        'catatan': 'Selalu tawarkan bantuan menghubungi bagian akademik.',
        'aktif': True})
    assert r.status_code == 200, r.json
    assert r.json['lingkup'] == 'hanya jadwal konsultasi dan hasil studi'
    ulang = client.get('/api/rules', headers=h).get_json()['chat_scope']
    assert ulang['ditolak'] == 'politik, agama, topik pribadi dosen'
    assert ulang['nada'] == 'singkat, maksimal 2 kalimat'


def test_batasan_benar_benar_masuk_prompt_chatbot(client):
    h_admin = login(client)
    client.put('/api/rules/chat-scope', headers=h_admin, json={
        'lingkup': 'hanya kehadiran dan nilai', 'ditolak': 'politik praktis',
        'nada': 'satu kalimat saja', 'catatan': 'Jangan sebut nama bagian apa pun.',
        'aktif': True})
    h = login(client, 'yanto@spram.local')
    terlihat = []
    with patch('backend.advisor_chat.call_model',
               side_effect=lambda m: terlihat.extend(m) or 'Baik.'):
        r = client.post('/api/students/STD-0001/assistant', headers=h,
                        json={'question': 'Bagaimana kehadirannya?'})
    assert r.status_code == 200
    prompt = json.dumps(terlihat)
    assert 'hanya kehadiran dan nilai' in prompt
    assert 'politik praktis' in prompt
    assert 'satu kalimat saja' in prompt
    assert 'Jangan sebut nama bagian apa pun.' in prompt


def test_mematikan_batasan_tetap_larang_bocor_teknis():
    prompt = _system_prompt({**DEFAULT_SCOPE, 'aktif': False})
    assert 'JSON' in prompt and 'token' in prompt
    assert 'LINGKUP HANYA' not in prompt


def test_batasan_terlalu_panjang_ditolak(client):
    h = login(client)
    r = client.put('/api/rules/chat-scope', headers=h, json={'lingkup': 'x' * 1300})
    assert r.status_code == 422 and 'maksimal' in r.json['error']


def test_dosen_tidak_boleh_mengubah_batasan(client):
    h = login(client, 'yanto@spram.local')
    assert client.put('/api/rules/chat-scope', headers=h,
                      json={'lingkup': 'apa saja'}).status_code == 403


def test_ubah_batasan_menggugurkan_cache_lama(client):
    admin = client
    h_admin = login(admin)
    dosen = admin.application.test_client()
    h = login(dosen, 'yanto@spram.local')
    panggilan = []
    with patch('backend.advisor_chat.call_model',
               side_effect=lambda m: panggilan.append(m) or 'Jawaban lama.'):
        dosen.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah?'})
        dosen.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah?'})
    assert len(panggilan) == 1, 'pertanyaan sama harus kena cache'
    assert admin.put('/api/rules/chat-scope', headers=h_admin,
                     json={**DEFAULT_SCOPE, 'nada': 'lebih singkat'}).status_code == 200
    with patch('backend.advisor_chat.call_model',
               side_effect=lambda m: panggilan.append(m) or 'Jawaban baru.'):
        r = dosen.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah?'})
    assert len(panggilan) == 2, 'batasan berubah -> cache lama tidak boleh dipakai'
    assert r.json['answer'] == 'Jawaban baru.'
