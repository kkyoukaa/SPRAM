import json, sqlite3, sys
from pathlib import Path
import pandas as pd, joblib
from sklearn.model_selection import train_test_split
ROOT = Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from backend.ml import UPDATE_FEATURES, LABELS, risk_band
from backend.expert import aturan_aktif, thresholds
frame = pd.read_csv(ROOT.parent / "data.csv", sep=";"); frame.columns=[c.strip() for c in frame.columns]
X, y = frame[UPDATE_FEATURES], frame.Target.map(LABELS)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.15, stratify=y, random_state=42)
model = joblib.load(ROOT / "artifacts/academic_update-random_forest-20260929143640/pipeline.joblib")
p = model.predict_proba(X_test)[:, 0]
con = sqlite3.connect(ROOT / "data/spram.sqlite"); con.row_factory = sqlite3.Row
rules = []
for r in con.execute("select * from rules where aktif=1 order by prioritas"):
    d = dict(r); k = json.loads(d.pop("kondisi_json") or "{}")
    d["kondisi"] = k.get("dan", []); d["kondisi_atau"] = k.get("atau", []); d["fallback"] = k.get("fallback", False)
    d["tindakan"] = json.loads(d.pop("tindakan_json") or "{}"); rules.append(d)
amb = thresholds()
per_rule_high = {}
high = 0; tanpa_aturan = 0; total_rule = 0
for i, (_, row) in enumerate(X_test.iterrows()):
    band = risk_band(float(p[i]))
    ids = [a["rule_id"] for a in aturan_aktif(row.to_dict(), [], band, rules, amb)]
    total_rule += len(ids)
    if not ids: tanpa_aturan += 1
    if band == "high":
        high += 1
        for rid in ids: per_rule_high[rid] = per_rule_high.get(rid, 0) + 1
print("risiko tinggi:", high, "| baris tanpa aturan:", tanpa_aturan, "| total aktivasi:", total_rule)
print("aktivasi pada 144 risiko tinggi:", json.dumps(per_rule_high, sort_keys=True))
print("--- kondisi tersimpan di DB ---")
for r in con.execute("select rule_id, kondisi_json from rules order by rule_id"):
    print(r[0], json.dumps(json.loads(r[1]), ensure_ascii=False))
