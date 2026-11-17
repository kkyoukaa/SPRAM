"""Kontrak endpoint chat: RBAC, batas input, rekomendasi dan fallback jujur."""
import json
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
        db.execute("INSERT INTO predictions(id,student_id,stage,snapshot_date,features,probabilities,predicted_class,risk_band,model_version,schema_version,drivers,protectors,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   ('p1', 'STD-0001', 'academic_update', '2026-10-01', json.dumps({'Debtor': 1, 'Gender': 1}),
                    json.dumps({'Dropout': .72, 'Enrolled': .18, 'Graduate': .10}), 'Dropout', 'high',
                    'v1', 'v1', json.dumps([{'feature': 'Debtor', 'shap': .22}]), '[]', None, '2026-10-01'))
        db.execute('INSERT INTO assignments(advisor_id,student_id) VALUES(2,?)', ('STD-0001',))
    return app.test_client()


def login(client, email):
    lines = Path(client.application.config['CREDENTIALS_FILE']).read_text().splitlines()
    password = lines[next(i for i, line in enumerate(lines) if email in line)+1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': email, 'password': password}, headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json['csrf_token']}


def test_chat_uses_context_not_fixed_intent(client):
    headers = login(client, 'yanto@spram.local')
    seen = []
    def fake(messages):
        seen.extend(messages)
        return 'Kalau pembayaran sudah selesai, periksa tanggal pembaruan data sebelum bertindak.'
    with patch('backend.advisor_chat.call_model', fake):
        r = client.post('/api/students/STD-0001/assistant', json={
            'question': 'Bagaimana jika tagihan sudah dibayar?',
            'history': [{'role': 'user', 'content': 'Tercatat ada tunggakan?'}]}, headers=headers)
    assert r.status_code == 200 and r.json['mode'] == 'ai'
    assert 'pembaruan data' in r.json['answer']
    assert 'NIM' not in json.dumps(seen)
    assert 'Gender' not in json.dumps(seen)
    assert 'tagihan sudah dibayar' in json.dumps(seen)


def test_model_timeout_honestly_reports_limit(client):
    headers = login(client, 'yanto@spram.local')
    with patch('backend.advisor_chat.call_model', side_effect=TimeoutError):
        r = client.post('/api/students/STD-0001/assistant', json={'question': 'Kapan beasiswa dibuka?'}, headers=headers)
    assert r.status_code == 200 and r.json['mode'] == 'terbatas'
    assert 'tidak dapat memastikan' in r.json['answer'].lower()


def test_recommendations_conditional_not_unverified_action(client):
    headers = login(client, 'yanto@spram.local')
    r = client.get('/api/students/STD-0001/recommendations')
    assert r.status_code == 200
    assert r.json['rekomendasi']
    first = r.json['rekomendasi'][0]
    assert first['verifikasi'] and first['sementara'] and first['jika_ya'] and first['jika_tidak']
    assert 'Gender' not in json.dumps(r.json)


def test_admin_still_denied(client):
    headers = login(client, 'admin@spram.local')
    assert client.post('/api/students/STD-0001/assistant', json={'question': 'apa kabar?'}, headers=headers).status_code == 403
    assert client.get('/api/students/STD-0001/recommendations').status_code == 403


def test_empty_question_rejected(client):
    headers = login(client, 'yanto@spram.local')
    r = client.post('/api/students/STD-0001/assistant', json={'question': '   '}, headers=headers)
    assert r.status_code == 422


def test_history_invalid_rejected(client):
    headers = login(client, 'yanto@spram.local')
    r = client.post('/api/students/STD-0001/assistant', json={'question': 'Apa?', 'history': 'not list'}, headers=headers)
    assert r.status_code == 422
