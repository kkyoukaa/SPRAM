"""Regresi: riwayat percakapan harus dimuat saat panel dibuka.

Bug asli: `list()` dipakai di StudentDetail.jsx tapi tidak diimpor, sehingga
pemuatan sesi melempar TypeError dan ditelan `catch` -> chat tampak kosong
setelah refresh / logout-login, padahal data ada di database.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = (ROOT / 'frontend/src/StudentDetail.jsx').read_text()


def test_semua_helper_api_yang_dipakai_diimpor():
    impor = re.search(r'import \{([^}]+)\} from "\./api";', SRC)
    assert impor, 'baris import dari ./api tidak ditemukan'
    tersedia = {x.strip() for x in impor.group(1).split(',')}
    for nama in ('api', 'post', 'list', 'date', 'pct'):
        if re.search(rf'\b{nama}\(', SRC):
            assert nama in tersedia, f'{nama}() dipakai tapi tidak diimpor'


def test_panel_memuat_sesi_dari_server():
    blok = SRC[SRC.index('export function AdvisorAssistant'):]
    assert 'api("/chat/sessions")' in blok
    assert 'list(d, "items").filter((s) => s.student_id === id)' in blok
    assert 'bukaSesi(daftar[0].id)' in blok


def test_gagal_muat_tidak_ditelan_diam_diam():
    blok = SRC[SRC.index('api("/chat/sessions")'):SRC.index('async function bukaSesi')]
    assert 'setRecoError' in blok, 'error pemuatan riwayat harus terlihat oleh dosen'
    assert '.catch(() => alive && setSiap(true))' not in blok


def test_bundle_produksi_memuat_pemuatan_sesi():
    bundle = next((ROOT / 'frontend/dist/assets').glob('index-*.js'))
    isi = bundle.read_text()
    assert '/chat/sessions' in isi
    assert 'chat-session' in isi
