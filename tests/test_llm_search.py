"""Pemilih model: kotak cari dengan daftar hasil (bukan dropdown panjang)."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def src():
    return (ROOT / 'frontend/src/LlmSettings.jsx').read_text()


def test_kotak_cari_menyatu_dengan_daftar_hasil():
    s = src()
    assert 'className="llm-search"' in s
    assert 'llm-search-icon' in s
    assert 'llm-search-clear' in s
    assert 'role="listbox"' in s
    assert 'role="option"' in s


def test_tidak_lagi_pakai_select_dropdown():
    s = src()
    assert '<select' not in s, 'pemilih model masih memakai dropdown'
    assert '<option' not in s


def test_hasil_bisa_diklik_untuk_memilih():
    s = src()
    blok = s[s.index('llm-list'):s.index('llm-empty')]
    assert 'onClick={() =>' in blok
    assert 'setPicked({ ...picked, [p.id]: m.id })' in blok
    assert 'aria-selected={terpilih === m.id}' in blok


def test_hasil_dibatasi_dan_ada_pesan_kosong():
    s = src()
    assert 'BATAS_TAMPIL' in s
    assert 'tersaring.slice(0, BATAS_TAMPIL)' in s
    assert 'Tidak ada model yang cocok' in s


def test_css_pemilih_model_ada():
    css = (ROOT / 'frontend/src/style.css').read_text()
    for kelas in ('.llm-search input', '.llm-list', '.llm-item', '.llm-item.selected', '.llm-empty'):
        assert kelas in css, kelas


def test_bundle_produksi_memuat_daftar_hasil():
    bundle = next((ROOT / 'frontend/dist/assets').glob('index-*.js'))
    isi = bundle.read_text()
    assert 'llm-search' in isi and 'llm-list' in isi
    assert 'Tidak ada model yang cocok' in isi
