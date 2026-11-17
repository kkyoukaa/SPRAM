"""Panel admin 'Ambang dari data latih' wajib punya keterangan untuk tiap ambang."""
import json
from pathlib import Path

DATA = Path(__file__).parents[1] / "data" / "rule_thresholds.json"


def test_setiap_ambang_punya_keterangan():
    ambang = json.loads(DATA.read_text())
    kunci = [k for k in ambang if k.endswith(("_p25", "_p75", "_p90"))]
    assert kunci, "tidak ada ambang terbaca"
    meta = ambang.get("meta") or {}
    assert set(kunci) == set(meta), f"meta tidak lengkap: {sorted(set(kunci) - set(meta))}"
    for k in kunci:
        m = meta[k]
        for field in ("judul", "arti", "dipakai"):
            assert m.get(field), f"{k}.{field} kosong"
        assert isinstance(ambang[k], (int, float)), f"{k} bukan angka"
