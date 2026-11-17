"""Hitung rekap aktivasi aturan R01-R08 pada data uji + cek efek kalibrasi LR."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import f1_score, log_loss, balanced_accuracy_score

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from backend.ml import UPDATE_FEATURES, LABELS, CLASSES, _models, expected_calibration_error, risk_band
from backend.expert import aturan_aktif, thresholds

frame = pd.read_csv(ROOT.parent / "data.csv", sep=";")
frame.columns = [str(c).strip() for c in frame.columns]
X, y = frame[UPDATE_FEATURES], frame.Target.map(LABELS)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.15, stratify=y, random_state=42)

model = joblib.load(ROOT / "artifacts/academic_update-random_forest-20260929143640/pipeline.joblib")
probs = model.predict_proba(X_test)
p_drop = probs[:, 0]

con = sqlite3.connect(ROOT / "data/spram.sqlite"); con.row_factory = sqlite3.Row
rules = []
for r in con.execute("select * from rules where aktif=1 order by prioritas"):
    d = dict(r)
    k = json.loads(d.pop("kondisi_json") or "{}")
    d["kondisi"] = k.get("dan", [])
    d["kondisi_atau"] = k.get("atau", [])
    d["fallback"] = k.get("fallback", False)
    d["tindakan"] = json.loads(d.pop("tindakan_json") or "{}")
    rules.append(d)

amb = thresholds()
counts = {r["rule_id"]: 0 for r in rules}
n_aktif_per_row = []
high_rows = 0
high_selain_r08 = 0
high_any = 0
uji_rows = len(X_test)
for i, (_, row) in enumerate(X_test.iterrows()):
    band = risk_band(float(p_drop[i]))
    aktif = aturan_aktif(row.to_dict(), [], band, rules, amb)
    ids = [a["rule_id"] for a in aktif]
    for rid in ids:
        counts[rid] += 1
    n_aktif_per_row.append(len(ids))
    if band == "high":
        high_rows += 1
        if ids:
            high_any += 1
        if any(r != "R08" for r in ids):
            high_selain_r08 += 1

print(f"data uji: {uji_rows} baris")
print("aktivasi per aturan:")
for rid in sorted(counts):
    print(f"  {rid}: {counts[rid]:4d}  ({counts[rid]/uji_rows*100:5.1f}%)")
print(f"baris tanpa aturan aktif: {sum(1 for n in n_aktif_per_row if n==0)}")
print(f"risiko tinggi: {high_rows}")
print(f"  memicu >=1 aturan (termasuk R08): {high_any} ({high_any/high_rows*100:.1f}%)")
print(f"  memicu >=1 aturan selain R08: {high_selain_r08} ({high_selain_r08/high_rows*100:.1f}%)")
print(f"rata-rata aturan aktif per baris: {np.mean(n_aktif_per_row):.2f}")

# --- efek kalibrasi LR ---
base = _models()["logistic_regression"]
cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
cv_mean = cross_val_score(base, X_train, y_train, cv=cv, scoring="f1_macro", n_jobs=1).mean()
base.fit(X_train, y_train)
p_raw = base.predict_proba(X_test)
cal = CalibratedClassifierCV(_models()["logistic_regression"], method="sigmoid", cv=3).fit(X_train, y_train)
p_cal = cal.predict_proba(X_test)
def rep(p, tag):
    pred = p.argmax(axis=1)
    print(f"  {tag}: macroF1={f1_score(y_test,pred,average='macro'):.4f} "
          f"balacc={balanced_accuracy_score(y_test,pred):.4f} "
          f"logloss={log_loss(y_test,p):.4f} ece={expected_calibration_error(y_test.to_numpy(),p):.4f} "
          f"recall_dropout={f1_score(y_test,pred,labels=[0],average='macro'):.4f}")
print(f"LR CV macroF1 (3-fold): {cv_mean:.4f}")
rep(p_raw, "sebelum kalibrasi")
rep(p_cal, "sesudah kalibrasi")
print(f"selisih CV - uji (terkalibrasi): {cv_mean - f1_score(y_test, p_cal.argmax(axis=1), average='macro'):+.4f}")
