"""Penyedia LLM kustom: CRUD endpoint + tarik daftar model, pilih model aktif.

API key disimpan terenkripsi, tidak pernah dikirim balik ke browser.
Modul ini murni soal konfigurasi; pemanggilan model ada di advisor_chat.
"""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

KEY_FILE = Path(__file__).parents[1] / 'data' / 'llm.key'
SCHEME = 'fernet'


def _fernet():
    from cryptography.fernet import Fernet
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes().strip()
    else:
        from cryptography.fernet import Fernet as F
        raw = F.generate_key()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(raw)
        os.chmod(KEY_FILE, 0o600)
    return Fernet(raw)


def enkripsi(teks):
    return _fernet().encrypt(str(teks).encode()).decode()


def dekripsi(token):
    if not token:
        return ''
    return _fernet().decrypt(str(token).encode()).decode()


def samarkan(key):
    """Hanya ekor kunci untuk ditampilkan di UI."""
    key = key or ''
    return ('•' * 8 + key[-4:]) if key else ''


def normalisasi_endpoint(url):
    """Terima base URL apa pun, kembalikan base /v1 tanpa trailing slash."""
    url = (url or '').strip().rstrip('/')
    if not url:
        raise ValueError('Endpoint wajib diisi')
    if not url.startswith(('http://10.', 'http://192.168.', 'http://127.0.0.1:',
                           'http://localhost:', 'https://')):
        raise ValueError('Endpoint harus jaringan internal atau HTTPS')
    for suffix in ('/chat/completions', '/models'):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if url.endswith('/v1'):
        return url
    return url + '/v1'


def _baca_json(response):
    """Sebagian gateway menempelkan 'data: [DONE]' setelah JSON selesai.

    Ambil blok JSON pertama yang seimbang, abaikan sisa body.
    """
    raw = response.read().decode('utf-8', 'replace').strip()
    if not raw:
        raise ValueError('Respons kosong dari endpoint')
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data, depth, start = None, 0, None
        for index, char in enumerate(raw):
            if char in '{[':
                if depth == 0:
                    start = index
                depth += 1
            elif char in '}]':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        data = json.loads(raw[start:index + 1])
                        break
                    except json.JSONDecodeError:
                        start = None
            if data is not None:
                break
        if data is None:
            raise ValueError('Respons endpoint bukan JSON yang valid')
    return data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data


def tarik_model(url, key, timeout=20):
    """GET {base}/models sesuai format OpenAI."""
    request = urllib.request.Request(url.rstrip('/') + '/models',
                                     headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = _baca_json(response)
    items = data.get('data') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError('Respons daftar model tidak dikenali')
    out = []
    for item in items:
        if isinstance(item, dict) and item.get('id'):
            out.append({'id': item['id'], 'owned_by': item.get('owned_by') or ''})
        elif isinstance(item, str):
            out.append({'id': item, 'owned_by': ''})
    if not out:
        raise ValueError('Endpoint tidak mengembalikan model apa pun')
    return sorted(out, key=lambda x: x['id'])


def uji_kirim(url, key, model, timeout=40):
    """Satu permintaan kecil untuk membuktikan model benar-benar menjawab."""
    payload = json.dumps({'model': model, 'messages': [
        {'role': 'user', 'content': 'Balas satu kata: siap'}],
        'max_tokens': 40, 'temperature': 0}).encode()
    request = urllib.request.Request(url.rstrip('/') + '/chat/completions', payload,
                                     {'Authorization': 'Bearer ' + key,
                                      'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = _baca_json(response)
    if data.get('error'):
        raise ValueError(str(data['error'])[:160])
    teks = (data.get('choices') or [{}])[0].get('message', {}).get('content') or ''
    if not teks.strip():
        raise ValueError('Model merespons kosong')
    return teks.strip()[:120]


def fingerprint(url, model):
    return hashlib.sha256(f'{url}|{model}'.encode()).hexdigest()[:16]


def b64(t):
    return base64.urlsafe_b64encode(str(t).encode()).decode()
