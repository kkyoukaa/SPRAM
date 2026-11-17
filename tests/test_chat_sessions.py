"""Sesi percakapan dosen wali: tersimpan, terpisah per dosen, tanpa istilah teknis."""
import json
import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

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


def login(client, email):
    lines = Path(client.application.config['CREDENTIALS_FILE']).read_text().splitlines()
    pw = lines[next(i for i, l in enumerate(lines) if email in l) + 1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': email, 'password': pw},
                    headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json['csrf_token']}


def test_sesi_tersimpan_dan_bisa_dibuka_lagi(client):
    h = login(client, 'yanto@spram.local')
    s = client.post('/api/chat/sessions', headers=h, json={'student_id': 'STD-0001'})
    assert s.status_code == 201
    sid = s.json['id']
    with patch('backend.advisor_chat.call_model', return_value='Coba cek administrasi dulu.'):
        r = client.post('/api/students/STD-0001/assistant', headers=h,
                        json={'question': 'Apa langkah saya?', 'session_id': sid})
    assert r.status_code == 200 and r.json['session']['id'] == sid
    assert r.json['session']['title'] == 'Apa langkah saya?'

    msgs = client.get(f'/api/chat/sessions/{sid}/messages').get_json()
    assert [m['role'] for m in msgs['items']] == ['user', 'assistant']
    assert msgs['items'][1]['content'] == 'Coba cek administrasi dulu.'

    daftar = client.get('/api/chat/sessions').get_json()['items']
    assert [x['id'] for x in daftar] == [sid]


def test_percakapan_lanjutan_membawa_konteks_sebelumnya(client):
    h = login(client, 'yanto@spram.local')
    sid = client.post('/api/chat/sessions', headers=h, json={'student_id': 'STD-0001'}).json['id']
    terlihat = []

    def fake(messages):
        terlihat.append(messages)
        return 'Baik, saya catat.'

    with patch('backend.advisor_chat.call_model', fake):
        client.post('/api/students/STD-0001/assistant', headers=h,
                    json={'question': 'Mahasiswa bilang sudah membayar.', 'session_id': sid})
        client.post('/api/students/STD-0001/assistant', headers=h,
                    json={'question': 'Lalu apa lagi?', 'session_id': sid})
    kiriman = json.dumps(terlihat[-1])
    assert 'Mahasiswa bilang sudah membayar.' in kiriman
    assert 'Lalu apa lagi?' in kiriman


def test_dosen_lain_tidak_bisa_membuka_sesi(client):
    h = login(client, 'yanto@spram.local')
    sid = client.post('/api/chat/sessions', headers=h, json={'student_id': 'STD-0001'}).json['id']
    assert client.get(f'/api/chat/sessions/{sid}/messages').status_code == 200
    # sesi milik dosen lain -> 404
    with sqlite3.connect(client.application.config['DATABASE']) as db:
        db.execute('UPDATE chat_sessions SET advisor_id=99 WHERE id=?', (sid,))
    assert client.get(f'/api/chat/sessions/{sid}/messages').status_code == 404


def test_admin_tidak_bisa_memakai_percakapan(client):
    h = login(client, 'admin@spram.local')
    assert client.get('/api/chat/sessions', headers=h).status_code == 403
    assert client.post('/api/chat/sessions', headers=h,
                       json={'student_id': 'STD-0001'}).status_code == 403


def test_hapus_sesi_bersih(client):
    h = login(client, 'yanto@spram.local')
    sid = client.post('/api/chat/sessions', headers=h, json={'student_id': 'STD-0001'}).json['id']
    with patch('backend.advisor_chat.call_model', return_value='ok'):
        client.post('/api/students/STD-0001/assistant', headers=h,
                    json={'question': 'Halo', 'session_id': sid})
    assert client.delete(f'/api/chat/sessions/{sid}', headers=h).status_code == 200
    assert client.get('/api/chat/sessions').get_json()['items'] == []
    with sqlite3.connect(client.application.config['DATABASE']) as db:
        assert db.execute('SELECT count(*) FROM chat_messages WHERE session_id=?', (sid,)).fetchone()[0] == 0


def test_tampilan_chat_tanpa_istilah_model():
    src = (ROOT / 'frontend/src/StudentDetail.jsx').read_text()
    panel = src[src.index('export function AdvisorAssistant'):]
    for terlarang in ('model percakapan', 'deepseek', 'Model aktif', 'llm'):
        assert terlarang.lower() not in panel.lower(), terlarang
    assert 'Percakapan baru' in panel
    assert 'chat-bubble' in panel
    assert 'Tulis pesan' in panel
