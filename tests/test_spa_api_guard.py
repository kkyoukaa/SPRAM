"""Endpoint API yang tidak ada harus 404 JSON, bukan 405/200 HTML dari SPA."""
from pathlib import Path

import pytest

from backend.app import create_app

ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'BOOTSTRAP_MODELS': False,
                      'DATABASE': str(tmp_path / 'db.sqlite'),
                      'CREDENTIALS_FILE': str(tmp_path / 'creds.txt'),
                      'ARTIFACT_DIR': str(ROOT / 'artifacts'), 'SECRET_KEY': 'test'})
    client = app.test_client()
    # rute tulis butuh sesi + CSRF; tanpa itu 403 CSRF menutupi 404
    lines = (tmp_path / 'creds.txt').read_text().splitlines()
    pw = lines[next(i for i, l in enumerate(lines) if 'admin@spram.local' in l) + 1].split(': ', 1)[1]
    token = client.get('/api/auth/me').json['csrf_token']
    r = client.post('/api/auth/login', json={'email': 'admin@spram.local', 'password': pw},
                    headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    client.environ_base['HTTP_X_CSRF_TOKEN'] = r.json['csrf_token']
    return client


def test_api_tidak_ada_balas_404_json(client):
    for method in ('get', 'post', 'delete', 'patch'):
        r = getattr(client, method)('/api/tidak-ada-sama-sekali')
        assert r.status_code == 404, (method, r.status_code)
        assert r.is_json, (method, r.headers.get('content-type'))
        assert r.get_json()['error_code'] == 'api_route_missing'
        assert r.get_json()['method'] == method.upper()


def test_halaman_aplikasi_tetap_disajikan(client):
    r = client.get('/penanganan')
    assert r.status_code == 200
    assert 'text/html' in r.headers.get('content-type', '')


def test_aset_statistik_tetap_disajikan(client):
    aset = list((ROOT / 'frontend/dist/assets').glob('index-*.js'))
    assert aset, 'bundle belum dibangun'
    r = client.get(f'/assets/{aset[0].name}')
    assert r.status_code == 200
