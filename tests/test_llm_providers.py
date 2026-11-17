"""Menu admin: kelola penyedia LLM custom dan pilih model aktif."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import create_app

ROOT = Path(__file__).parents[1]
FAKE_MODELS = [{'id': 'in/cb/deepseek-v4.1-flash', 'owned_by': 'in'},
               {'id': 'kr/claude-haiku-4.5', 'owned_by': 'kr'}]


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'BOOTSTRAP_MODELS': False,
                      'DATABASE': str(tmp_path / 'db.sqlite'),
                      'CREDENTIALS_FILE': str(tmp_path / 'creds.txt'),
                      'ARTIFACT_DIR': str(ROOT / 'artifacts'), 'SECRET_KEY': 'test'})
    return app.test_client()


def login(client, email='admin@spram.local'):
    lines = Path(client.application.config['CREDENTIALS_FILE']).read_text().splitlines()
    pw = lines[next(i for i, l in enumerate(lines) if email in l) + 1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': email, 'password': pw},
                    headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    return {'X-CSRF-Token': r.json['csrf_token']}


def test_tambah_penyedia_menarik_semua_model(client):
    headers = login(client)
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS):
        r = client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'Gateway Internal', 'base_url': 'http://10.168.20.228:20128',
            'api_key': 'rahasia-sekali'})
    assert r.status_code == 201, r.json
    assert r.json['model_count'] == 2
    assert {m['id'] for m in r.json['models']} == {m['id'] for m in FAKE_MODELS}
    assert r.json['base_url'] == 'http://10.168.20.228:20128/v1'


def test_api_key_tidak_pernah_keluar_di_respons(client):
    headers = login(client)
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS):
        client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'G', 'base_url': 'http://10.1.1.1:20128', 'api_key': 'SUPER-SECRET-KEY'})
    body = client.get('/api/admin/llm/providers').get_json()
    teks = json.dumps(body)
    assert 'SUPER-SECRET-KEY' not in teks
    assert body['items'][0]['api_key_masked'].endswith('KEY')
    assert body['items'][0]['api_key_masked'].startswith('•')


def test_pilih_model_aktif_divalidasi_dan_diuji(client):
    headers = login(client)
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS):
        pid = client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'G', 'base_url': 'http://10.1.1.1:20128', 'api_key': 'k'}).json['id']
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS), \
         patch('backend.llm_providers.uji_kirim', return_value='siap'):
        ok = client.post('/api/admin/llm/active', headers=headers,
                         json={'provider_id': pid, 'model': 'in/cb/deepseek-v4.1-flash'})
        assert ok.status_code == 200 and ok.json['probe'] == 'siap'
        salah = client.post('/api/admin/llm/active', headers=headers,
                            json={'provider_id': pid, 'model': 'model-tidak-ada'})
        assert salah.status_code == 422
    aktif = client.get('/api/admin/llm/active').get_json()
    assert aktif['model'] == 'in/cb/deepseek-v4.1-flash'
    assert aktif['provider_name'] == 'G'


def test_model_gagal_menjawab_tidak_disimpan(client):
    headers = login(client)
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS):
        pid = client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'G', 'base_url': 'http://10.1.1.1:20128', 'api_key': 'k'}).json['id']
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS), \
         patch('backend.llm_providers.uji_kirim', side_effect=TimeoutError):
        r = client.post('/api/admin/llm/active', headers=headers,
                        json={'provider_id': pid, 'model': 'kr/claude-haiku-4.5'})
    assert r.status_code == 422 and 'tidak dapat menjawab' in r.json['error']
    assert client.get('/api/admin/llm/active').json['model'] is None


def test_hapus_penyedia_mengosongkan_model_aktif(client):
    headers = login(client)
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS):
        pid = client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'G', 'base_url': 'http://10.1.1.1:20128', 'api_key': 'k'}).json['id']
    with patch('backend.llm_providers.tarik_model', return_value=FAKE_MODELS), \
         patch('backend.llm_providers.uji_kirim', return_value='siap'):
        client.post('/api/admin/llm/active', headers=headers,
                    json={'provider_id': pid, 'model': 'kr/claude-haiku-4.5'})
    assert client.delete(f'/api/admin/llm/providers/{pid}', headers=headers).status_code == 200
    assert client.get('/api/admin/llm/active').json['model'] is None
    assert client.get('/api/admin/llm/providers').json['items'] == []


def test_endpoint_eksternal_ditolak(client):
    headers = login(client)
    r = client.post('/api/admin/llm/providers', headers=headers, json={
        'name': 'X', 'base_url': 'http://evil.example.com/v1', 'api_key': 'k'})
    assert r.status_code == 422 and 'internal' in r.json['error']


def test_endpoint_menolak_key_tidak_menyimpan_apa_pun(client):
    import urllib.error
    headers = login(client)
    with patch('backend.llm_providers.tarik_model',
               side_effect=urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)):
        r = client.post('/api/admin/llm/providers', headers=headers, json={
            'name': 'G', 'base_url': 'http://10.1.1.1:20128', 'api_key': 'salah'})
    assert r.status_code == 422 and '401' in r.json['error']
    assert client.get('/api/admin/llm/providers').json['items'] == []


def test_dosen_wali_tidak_boleh_akses_menu_llm(client):
    headers = login(client, 'yanto@spram.local')
    assert client.get('/api/admin/llm/providers', headers=headers).status_code == 403
    assert client.post('/api/admin/llm/active', headers=headers,
                       json={'provider_id': 'x', 'model': 'y'}).status_code == 403
