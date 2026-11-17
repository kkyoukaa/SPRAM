import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, log_loss, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

SEMESTER_FEATURES = [
    f"Curricular units {semester} sem ({kind})"
    for semester in ("1st", "2nd")
    for kind in ("credited", "enrolled", "evaluations", "approved", "grade", "without evaluations")
]
ALL_FEATURES = [
    "Marital status", "Application mode", "Application order", "Course",
    "Daytime/evening attendance", "Previous qualification", "Previous qualification (grade)",
    "Nacionality", "Mother's qualification", "Father's qualification", "Mother's occupation",
    "Father's occupation", "Admission grade", "Displaced", "Educational special needs", "Debtor",
    "Tuition fees up to date", "Gender", "Scholarship holder", "Age at enrollment", "International",
] + SEMESTER_FEATURES[:6] + SEMESTER_FEATURES[6:] + ["Unemployment rate", "Inflation rate", "GDP"]
INTAKE_FEATURES = [x for x in ALL_FEATURES if x not in SEMESTER_FEATURES]
UPDATE_FEATURES = ALL_FEATURES
CLASSES = ["Dropout", "Enrolled", "Graduate"]
LABELS = {name: i for i, name in enumerate(CLASSES)}


def normalize_columns(frame):
    frame = frame.copy()
    frame.columns = [str(x).strip() for x in frame.columns]
    return frame


def risk_band(probability):
    return "high" if probability >= .7 else "medium" if probability >= .4 else "low"


def expected_calibration_error(y, probabilities, bins=10):
    confidence = probabilities.max(axis=1)
    correct = probabilities.argmax(axis=1) == y
    result = 0.0
    for low in np.linspace(0, 1, bins, endpoint=False):
        mask = (confidence >= low) & (confidence < low + 1 / bins)
        if mask.any():
            result += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(result)


def schema_for(frame, features, stage, model_version):
    fields, example = [], {}
    integer_names = {x for x in features if "grade" not in x.lower() and x not in {"Unemployment rate", "Inflation rate", "GDP"}}
    for name in features:
        series = frame[name]
        integer = name in integer_names
        field = {"name": name, "label": name, "type": "integer" if integer else "number", "required": True,
                 "min": float(series.min()), "max": float(series.max()), "observed_min": float(series.min()), "observed_max": float(series.max())}
        example[name] = int(series.median()) if integer else float(series.median())
        fields.append(field)
    return {"stage": stage, "schema_version": f"{stage}-schema-1", "model_version": model_version, "features": fields, "example": example}


def _models(quick=False):
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=700, class_weight="balanced", random_state=42)),
        "random_forest": RandomForestClassifier(n_estimators=50 if quick else 180, class_weight="balanced", min_samples_leaf=2, n_jobs=2, random_state=42),
        "xgboost": XGBClassifier(n_estimators=40 if quick else 150, max_depth=4, learning_rate=.08, subsample=.85, colsample_bytree=.85, n_jobs=2, random_state=42, eval_metric="mlogloss"),
    }


def train_stage(dataset, stage, artifact_root, quick=False, progress=None):
    artifact_root = Path(artifact_root)
    frame = normalize_columns(pd.read_csv(dataset, sep=";"))
    features = INTAKE_FEATURES if stage == "intake" else UPDATE_FEATURES
    X, y = frame[features], frame.Target.map(LABELS)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.15, stratify=y, random_state=42)
    cv = StratifiedKFold(n_splits=2 if quick else 3, shuffle=True, random_state=42)
    reports, fitted = {}, {}
    for index, (name, model) in enumerate(_models(quick).items(), 1):
        scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="f1_macro", n_jobs=1)
        calibrated = CalibratedClassifierCV(model, method="sigmoid", cv=2 if quick else 3).fit(X_train, y_train)
        probabilities = calibrated.predict_proba(X_test)
        predicted = probabilities.argmax(axis=1)
        reports[name] = {
            "cv_macro_f1_mean": float(scores.mean()), "macro_f1": float(f1_score(y_test, predicted, average="macro")),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
            "recall_dropout": float(recall_score(y_test, predicted, labels=[0], average="macro")),
            "log_loss": float(log_loss(y_test, probabilities)), "ece": expected_calibration_error(y_test.to_numpy(), probabilities),
            "confusion_matrix": confusion_matrix(y_test, predicted, labels=[0, 1, 2]).tolist(),
            "per_class_recall": {CLASSES[i]: float(recall_score(y_test, predicted, labels=[i], average="macro")) for i in range(3)},
        }
        fitted[name] = calibrated
        if progress:
            progress(index * 25)
    baseline = reports["logistic_regression"]
    best = max(reports, key=lambda name: reports[name]["macro_f1"])
    if best != "logistic_regression" and reports[best]["macro_f1"] < baseline["macro_f1"] + .02:
        best = "logistic_regression"
    ts = pd.Timestamp.utcnow().strftime('%Y%m%d%H%M%S')
    all_versions = {}
    for alg_name, calibrated_model in fitted.items():
        version = f"{stage}-{alg_name}-{ts}"
        output = artifact_root / version
        output.mkdir(parents=True, exist_ok=True)
        joblib.dump(calibrated_model, output / "pipeline.joblib")
        schema = schema_for(frame, features, stage, version)
        background = X_train.sample(min(100, len(X_train)), random_state=42)
        est = getattr(getattr(calibrated_model, "calibrated_classifiers_", [None])[0], "estimator", calibrated_model)
        importance = np.abs(est.feature_importances_) if hasattr(est, "feature_importances_") else np.ones(len(features))
        shap_global = sorted(
            ({"feature": f, "importance": float(v)} for f, v in zip(features, importance)),
            key=lambda x: x["importance"], reverse=True)
        checksum = hashlib.sha256(Path(dataset).read_bytes()).hexdigest()
        files = {
            "feature_schema.json": schema, "category_map.json": {},
            "metrics.json": {"champion_algorithm": best, "candidates": reports},
            "calibration.json": {name: {"ece": report["ece"], "log_loss": report["log_loss"]} for name, report in reports.items()},
            "thresholds.json": {"low": .4, "high": .7, "version": "risk-v1"},
            "shap_config.json": {"method": "permutation", "global": shap_global},
            "metadata.json": {"dataset_checksum": checksum, "source_filename": Path(dataset).name, "seed": 42, "features": features, "classes": CLASSES},
        }
        for filename, value in files.items():
            (output / filename).write_text(json.dumps(value, indent=2))
        background.to_csv(output / "shap_background.csv", index=False)
        (output / "model_card.md").write_text(
            f"# {version}\n\nStage: {stage}\nAlgorithm: {alg_name}\nDataset: UCI 697 ({checksum})\n\n"
            f"Academic prototype; not validated for Indonesian students. Predictions support human review and must not determine sanctions.\n")
        artifact_checksum = hashlib.sha256((output / "pipeline.joblib").read_bytes()).hexdigest()
        all_versions[alg_name] = {"version": version, "path": str(output), "checksum": artifact_checksum, "metrics": reports[alg_name]}
    return {"best": best, "all_versions": all_versions, "metrics": {"champion_algorithm": best, "candidates": reports}}


def explain(model, features, values, background_path):
    # Local permutation against training medians gives signed, model-grounded dropout contributions.
    # One batched predict_proba for row + every counterfactual + baseline: ~30x faster than per-feature calls.
    row = pd.DataFrame([values], columns=features)
    baseline_values = pd.read_csv(background_path)[features].median()
    variants = [row]
    for feature in features:
        changed = row.copy()
        changed[feature] = baseline_values[feature]
        variants.append(changed)
    variants.append(pd.DataFrame([baseline_values], columns=features))
    probs = model.predict_proba(pd.concat(variants, ignore_index=True))[:, 0]
    row_p = float(probs[0]); base_p = float(probs[-1])
    contributions = [{"feature": feature, "value": float(row.iloc[0][feature]),
                      "shap": row_p - float(probs[i + 1])} for i, feature in enumerate(features)]
    drivers = sorted((x for x in contributions if x["shap"] > 0), key=lambda x: x["shap"], reverse=True)[:5]
    protectors = sorted((x for x in contributions if x["shap"] < 0), key=lambda x: x["shap"])[:3]
    for x in drivers: x["direction"] = "increase"
    for x in protectors: x["direction"] = "decrease"
    return base_p, drivers, protectors
