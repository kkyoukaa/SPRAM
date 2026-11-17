"""Cache jawaban: pertanyaan serupa -> jawaban sama tanpa panggilan model baru."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import create_app
from backend.chat_cache import kunci, normalisasi

ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'BOOTSTRAP_MODELS': False,
                      'DATABASE': str(tmp_path / 'db.sqlite'),
                      'CREDENTIALS_FILE': str(tmp_path / 'creds.txt'),
                      'ARTIFACT_DIR': str(ROOT / 'artifacts'), 'SECRET_KEY': 'test'})
    with sqlite3.connect(app.config['DATABASE']) as db:
        for sid in ('STD-0001', 'STD-0002'):
            db.execute("INSERT INTO predictions(id,student_id,stage,snapshot_date,features,probabilities,"
                       "predicted_class,risk_band,model_version,schema_version,drivers,protectors,"
                       "idempotency_key,created_at) VALUES(?,?,'academic_update','2026-10-01',?,?,"
                       "'Dropout','high','v1','v1',?,'[]',NULL,'2026-10-01')",
                       (f'p-{sid}', sid, json.dumps({'Debtor': 1}),
                        json.dumps({'Dropout': .72, 'Enrolled': .2, 'Graduate': .08}),
                        json.dumps([{'feature': 'Debtor', 'shap': .22}])))
        db.execute("INSERT INTO assignments(advisor_id,student_id) VALUES(2,'STD-0001')")
        db.execute("INSERT INTO assignments(advisor_id,student_id) VALUES(2,'STD-0002')")
    return app.test_client()


def login(client):
    lines = Path(client.application.config['CREDENTIALS_FILE']).read_text().splitlines()
    pw = lines[next(i for i, l in enumerate(lines) if 'yanto@spram.local' in l) + 1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': 'yanto@spram.local', 'password': pw},
                    headers={'X-CSRF-Token': token})
    return {'X-CSRF-Token': r.json['csrf_token']}


def test_normalisasi_menyamakan_ragam_kalimat():
    a = normalisasi('Kenapa mahasiswa ini berisiko tinggi?')
    b = normalisasi('knp mhs ini resiko tinggi')
    assert a == b
    assert normalisasi('Apa langkah saya?') == normalisasi('saran tindakan saya?')


def test_pertanyaan_sama_hanya_panggil_model_sekali(client):
    h = login(client)
    panggilan = []

    def fake(messages):
        panggilan.append(messages)
        return 'Periksa pembayaran dulu, lalu cocokkan ke bagian keuangan.'

    with patch('backend.advisor_chat.call_model', fake):
        r1 = client.post('/api/students/STD-0001/assistant', headers=h,
                         json={'question': 'Apa langkah saya?'})
        r2 = client.post('/api/students/STD-0001/assistant', headers=h,
                         json={'question': 'apa langkah saya'})
        r3 = client.post('/api/students/STD-0001/assistant', headers=h,
                         json={'question': 'saran tindakan saya?'})
    assert r1.json['cached'] is False and r2.json['cached'] is True and r3.json['cached'] is True
    assert r1.json['answer'] == r2.json['answer'] == r3.json['answer']
    assert len(panggilan) == 1, f'model dipanggil {len(panggilan)}x, seharusnya 1x'


def test_pertanyaan_berbeda_tetap_panggil_model(client):
    h = login(client)
    panggilan = []
    with patch('backend.advisor_chat.call_model',
               side_effect=lambda m: panggilan.append(m) or 'Jawaban berbeda.'):
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah saya?'})
        client.post('/api/students/STD-0001/assistant', headers=h,
                    json={'question': 'Seberapa yakin analisis ini?'})
    assert len(panggilan) == 2


def test_konteks_beda_tidak_berbagi_cache(client):
    h = login(client)
    with sqlite3.connect(client.application.config['DATABASE']) as db:
        db.execute("UPDATE predictions SET risk_band='low', probabilities=? WHERE student_id='STD-0002'",
                   (json.dumps({'Dropout': .12, 'Enrolled': .5, 'Graduate': .38}),))
    panggilan = []
    with patch('backend.advisor_chat.call_model',
               side_effect=lambda m: panggilan.append(m) or 'Jawaban sesuai konteks.'):
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah saya?'})
        client.post('/api/students/STD-0002/assistant', headers=h, json={'question': 'Apa langkah saya?'})
    assert len(panggilan) == 2, 'mahasiswa beda konteks tidak boleh berbagi jawaban'


def test_mode_terbatas_tidak_disimpan_ke_cache(client):
    h = login(client)
    with patch('backend.advisor_chat.call_model', side_effect=TimeoutError):
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah saya?'})
    with sqlite3.connect(client.application.config['DATABASE']) as db:
        assert db.execute('SELECT count(*) FROM chat_cache').fetchone()[0] == 0


def test_cache_menghitung_hit(client):
    h = login(client)
    with patch('backend.advisor_chat.call_model', return_value='Sama.'):
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'Apa langkah?'})
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'apa langkah'})
        client.post('/api/students/STD-0001/assistant', headers=h, json={'question': 'langkah apa?'})
    with sqlite3.connect(client.application.config['DATABASE']) as db:
        hits = db.execute('SELECT hits FROM chat_cache').fetchone()[0]
    assert hits == 2, hits
