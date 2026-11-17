import csv
import io
import json
import os
import time
from pathlib import Path

import pytest

from backend.app import create_app
from backend.ml import INTAKE_FEATURES, UPDATE_FEATURES, risk_band


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "BOOTSTRAP_MODELS": True, "DATABASE": str(tmp_path / "test.sqlite"), "ARTIFACT_DIR": str(tmp_path / "artifacts"), "CREDENTIALS_FILE": str(tmp_path / "demo-credentials.txt"), "SECRET_KEY": "test-secret", "DATASET": str(Path(__file__).parents[2] / "data.csv")})
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    return client.get("/api/auth/me").get_json()["csrf_token"]


def login(client, email="admin@spram.local", password=None):
    if password is None:
        lines = Path(client.application.config["CREDENTIALS_FILE"]).read_text().splitlines()
        for index, line in enumerate(lines):
            if email in line:
                password = lines[index + 1].split(": ", 1)[1]
                break
        else:
            raise AssertionError(f"kredensial untuk {email} tidak ada di file")
    token = csrf(client)
    response = client.post("/api/auth/login", json={"email": email, "password": password}, headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["csrf_token"]


def sample(stage="intake"):
    schema = json.loads((Path(__file__).parents[1] / "artifacts" / "active.json").read_text())[stage]
    return schema


def payload_from_schema(client, stage="intake", student_id="STD-0001"):
    schema = client.get(f"/api/model-schemas/{stage}/active").get_json()
    return {"student_id": student_id, "stage": stage, "snapshot_date": "2026-09-23", "schema_version": schema["schema_version"], "features": schema["example"]}


def test_public_health_and_csrf_login(client):
    assert client.get("/api/health").get_json()["status"] == "ok"
    assert client.post("/api/auth/login", json={}).status_code == 403
    token = csrf(client)
    assert client.post("/api/auth/login", json={"email": "x", "password": "x"}, headers={"X-CSRF-Token": token}).status_code == 401


def test_risk_thresholds():
    assert [risk_band(x) for x in (0.39, 0.4, 0.699, 0.7)] == ["low", "medium", "medium", "high"]


def test_manual_prediction_schema_has_human_friendly_metadata(client):
    login(client)
    schema = client.get("/api/model-schemas/academic_update/active").get_json()
    fields = {field["name"]: field for field in schema["features"]}
    assert fields["Debtor"]["label"] == "Memiliki tunggakan"
    assert fields["Debtor"]["categories"] == [{"value": 0, "label": "Tidak"}, {"value": 1, "label": "Ya"}]
    assert fields["Marital status"]["categories"][0] == {"value": 1, "label": "Lajang"}
    assert fields["Admission grade"]["help"] == "Skala 0–200"
    for name in ("Application mode", "Course", "Previous qualification", "Nacionality", "Mother's qualification", "Father's qualification", "Mother's occupation", "Father's occupation"):
        assert fields[name]["categories"], name
    assert fields["Application mode"]["categories"][0]["label"] == "Tahap 1 - jalur umum"
    labels = [option["label"].lower() for field in fields.values() for option in field.get("categories", [])]
    assert not any(term in label for label in labels for term in ("1st phase", "higher education", "unknown", "not completed", "student", "management", "nursing"))


def test_prediction_validation_history_and_idempotency(client):
    token = login(client)
    body = payload_from_schema(client)
    bad = dict(body)
    bad["features"] = {}
    response = client.post("/api/predictions", json=bad, headers={"X-CSRF-Token": token})
    assert response.status_code == 422 and response.get_json()["error"]["fields"]
    body["idempotency_key"] = "same"
    first = client.post("/api/predictions", json=body, headers={"X-CSRF-Token": token})
    second = client.post("/api/predictions", json=body, headers={"X-CSRF-Token": token})
    assert first.status_code == 201
    result = first.get_json()
    assert result["id"] == second.get_json()["id"]
    assert set(result["probabilities"]) == {"Dropout", "Enrolled", "Graduate"}
    assert abs(sum(result["probabilities"].values()) - 1) < 1e-9
    assert result["top_drivers"] and result["model_version"]
    timeline = client.get("/api/students/STD-0001/timeline").get_json()
    assert len(timeline["predictions"]) == 1


def test_manual_prediction_warns_when_student_already_predicted(client):
    token = login(client)
    body = payload_from_schema(client, stage="academic_update", student_id="DUP-MANUAL")
    assert client.post("/api/predictions", json=body, headers={"X-CSRF-Token": token}).status_code == 201
    duplicate = client.post("/api/predictions", json=body, headers={"X-CSRF-Token": token})
    assert duplicate.status_code == 409
    assert "sudah" in duplicate.get_json()["error"].lower()


def test_csv_skips_existing_and_repeated_student_ids(client):
    token = login(client)
    headers = {"X-CSRF-Token": token}
    existing = payload_from_schema(client, stage="academic_update", student_id="DUP-EXISTING")
    assert client.post("/api/predictions", json=existing, headers=headers).status_code == 201
    schema = client.get("/api/model-schemas/academic_update/active").get_json()
    fields = ["student_id", "snapshot_date"] + [x["name"] for x in schema["features"]]
    output = io.StringIO(); writer = csv.DictWriter(output, fields, delimiter=";"); writer.writeheader()
    for sid in ("DUP-EXISTING", "DUP-IN-FILE", "DUP-IN-FILE", "UNIQUE"):
        writer.writerow({**schema["example"], "student_id": sid, "snapshot_date": "2026-10-05"})
    response = client.post("/api/batch-jobs", data={"stage": "academic_update", "file": (io.BytesIO(output.getvalue().encode()), "input.csv")}, headers=headers)
    assert response.status_code == 201
    job = response.get_json()
    # Snapshot berbeda dianggap prediksi baru; hanya duplikat dalam file yang dilewati.
    assert job["valid_count"] == 3
    assert job["skipped_count"] == 1
    assert {x["student_id"] for x in job["skipped"]} == {"DUP-IN-FILE"}
    assert job["can_predict"] is True


def test_advisor_scope_and_admin_rbac(client):
    token = login(client, "yanto@spram.local")
    assert client.get("/api/students/STD-0002/timeline").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    body = payload_from_schema(client, student_id="STD-0002")
    assert client.post("/api/predictions", json=body, headers={"X-CSRF-Token": token}).status_code == 403


def test_student_directory_search_filter_and_summary_classes(client):
    token = login(client)
    first = client.post("/api/predictions", json=payload_from_schema(client), headers={"X-CSRF-Token": token}).get_json()
    students = client.get("/api/students?q=STD-0001&prediction_class=" + first["predicted_class"]).get_json()
    assert students["total"] == 1
    assert students["items"][0]["student_id"] == "STD-0001"
    assert students["items"][0]["latest_prediction"]["predicted_class"] == first["predicted_class"]
    assert client.get("/api/students?q=tidak-ada").get_json()["total"] == 0
    summary = client.get("/api/dashboard/summary").get_json()
    assert set(summary["class_distribution"]) == {"Dropout", "Enrolled", "Graduate"}
    assert sum(summary["class_distribution"].values()) == 1


def tetapkan_ke_dosen(client, headers, sid="STD-0001"):
    """Penanganan hanya untuk dosen wali, jadi mahasiswa harus dibimbing dulu."""
    dosen = next(u for u in client.get("/api/admin/users").get_json()["items"] if u["email"] == "yanto@spram.local")
    r = client.post("/api/admin/assignments", headers=headers, json={"advisor_id": dosen["id"], "student_ids": [sid]})
    assert r.status_code in (201, 409), r.get_json()


def test_intervention_assistant_and_dashboard(client):
    token = login(client)
    result = client.post("/api/predictions", json=payload_from_schema(client), headers={"X-CSRF-Token": token}).get_json()
    tetapkan_ke_dosen(client, {"X-CSRF-Token": token})
    advisor_token = login(client, "yanto@spram.local")
    answer = client.post("/api/assistant", json={"prediction_id": result["id"], "intent": "why"}, headers={"X-CSRF-Token": advisor_token})
    assert answer.status_code == 200 and "bukan" in answer.get_json()["disclaimer"].lower()
    intervention = client.post("/api/interventions", json={"student_id": "STD-0001", "prediction_id": result["id"], "type": "academic", "note": "Hubungi mahasiswa", "due_date": "2026-10-01", "status": "planned"}, headers={"X-CSRF-Token": advisor_token})
    assert intervention.status_code == 201
    changed = client.patch(f"/api/interventions/{intervention.get_json()['id']}", json={"status": "completed"}, headers={"X-CSRF-Token": advisor_token})
    assert changed.get_json()["status"] == "completed"
    login(client)
    assert client.get("/api/dashboard/summary").get_json()["total_predictions"] == 1


def xlsx_bytes(headers, rows):
    import zipfile
    from xml.sax.saxutils import escape
    strings = headers + [str(value) for row in rows for value in row]
    shared = "<?xml version='1.0'?><sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>" + "".join(f"<si><t>{escape(value)}</t></si>" for value in strings) + "</sst>"
    cells = []
    index = 0
    for row_number, row in enumerate([headers] + rows, 1):
        row_cells = []
        for column_number, _ in enumerate(row, 1):
            column = chr(64 + column_number)
            row_cells.append(f'<c r="{column}{row_number}" t="s"><v>{index}</v></c>')
            index += 1
        cells.append(f'<row r="{row_number}">{"".join(row_cells)}</row>')
    sheet = "<?xml version='1.0'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>" + "".join(cells) + "</sheetData></worksheet>"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def test_batch_accepts_excel_xlsx_with_same_validation_as_csv(client):
    token = login(client)
    schema = client.get("/api/model-schemas/intake/active").get_json()
    fields = ["student_id", "snapshot_date"] + [x["name"] for x in schema["features"]]
    row = ["XLSX-1", "2026-10-05"] + [schema["example"][name] for name in fields[2:]]
    response = client.post("/api/batch-jobs", data={"stage": "intake", "file": (io.BytesIO(xlsx_bytes(fields, [row])), "prediksi.xlsx")}, headers={"X-CSRF-Token": token})
    assert response.status_code == 201
    job = response.get_json()
    assert job["valid_count"] == 1
    assert job["invalid_count"] == 0
    assert job["preview"][0]["student_id"] == "XLSX-1"


def test_csv_validation_blocks_prediction_and_reports_repairs(client):
    token = login(client)
    headers = {"X-CSRF-Token": token}
    wrong_type = client.post("/api/batch-jobs", data={"stage": "academic_update", "file": (io.BytesIO(b"x"), "input.txt")}, headers=headers)
    assert wrong_type.status_code == 422
    assert "CSV" in wrong_type.get_json()["error"]

    schema = client.get("/api/model-schemas/academic_update/active").get_json()
    fields = ["student_id", "snapshot_date"] + [x["name"] for x in schema["features"]]
    fields[2] = "Marital stats"
    output = io.StringIO(); writer = csv.DictWriter(output, fields, delimiter=";"); writer.writeheader()
    row = {name: schema["example"].get(name, "") for name in fields}
    row.update(student_id="STD-BAD", snapshot_date="2026-10-05", **{"Marital stats": ""})
    writer.writerow(row)
    response = client.post("/api/batch-jobs", data={"stage": "academic_update", "file": (io.BytesIO(output.getvalue().encode()), "input.csv")}, headers=headers)
    assert response.status_code == 422
    data = response.get_json()
    assert "Marital status" in data["missing_columns"]
    assert "Marital stats" in data["unknown_columns"]
    assert data["can_predict"] is False


def test_batch_run_rejects_job_with_invalid_rows(client):
    token = login(client)
    schema = client.get("/api/model-schemas/academic_update/active").get_json()
    fields = ["student_id", "snapshot_date"] + [x["name"] for x in schema["features"]]
    output = io.StringIO(); writer = csv.DictWriter(output, fields, delimiter=";"); writer.writeheader()
    valid = {**schema["example"], "student_id": "VALID", "snapshot_date": "2026-10-05"}; writer.writerow(valid)
    invalid = dict(valid); invalid["student_id"] = "INVALID"; invalid[UPDATE_FEATURES[0]] = ""; writer.writerow(invalid)
    job = client.post("/api/batch-jobs", data={"stage": "academic_update", "file": (io.BytesIO(output.getvalue().encode()), "input.csv")}, headers={"X-CSRF-Token": token}).get_json()
    response = client.post(f"/api/batch-jobs/{job['id']}/run", json={}, headers={"X-CSRF-Token": token})
    assert response.status_code == 409
    assert "perbaiki" in response.get_json()["error"].lower()


def test_batch_partial_and_formula_safe_exports(client):
    token = login(client)
    schema = client.get("/api/model-schemas/intake/active").get_json()
    fields = ["student_id", "snapshot_date", "prediction_stage"] + [x["name"] for x in schema["features"]]
    output = io.StringIO()
    writer = csv.DictWriter(output, fields, delimiter=";")
    writer.writeheader()
    row = {**schema["example"], "student_id": "STD-0001", "snapshot_date": "2026-09-23", "prediction_stage": "intake"}
    row["student_id"] = "=BAD"
    writer.writerow(row)
    response = client.post("/api/batch-jobs", data={"stage": "intake", "file": (io.BytesIO(output.getvalue().encode()), "input.csv")}, headers={"X-CSRF-Token": token})
    assert response.status_code == 201
    job = response.get_json()
    assert (job["valid_count"], job["invalid_count"]) == (1, 0)
    run = client.post(f"/api/batch-jobs/{job['id']}/run", json={}, headers={"X-CSRF-Token": token})
    assert run.status_code == 202
    for _ in range(100):
        done = client.get(f"/api/batch-jobs/{job['id']}").get_json()
        if done["status"] in {"completed", "partial", "failed"}:
            break
        time.sleep(.02)
    assert done["status"] == "completed" and len(done["results"]) == 1
    result = done["results"][0]
    assert result["status"] == "success"
    assert set(result["probabilities"]) == {"Dropout", "Enrolled", "Graduate"}
    exported = client.get(f"/api/batch-jobs/{job['id']}/export").data.decode()
    assert "student_id,prediction,status,probability_dropout,probability_enrolled,probability_graduate" in exported
    assert "'=BAD" in exported


def test_admin_training_registry_promotion_and_rollback(client):
    token = login(client)
    response = client.post("/api/admin/training-jobs", json={"stage": "intake", "dataset_version": "uci-697", "config": {"quick": True}}, headers={"X-CSRF-Token": token})
    assert response.status_code == 202
    job_id = response.get_json()["id"]
    for _ in range(300):
        job = client.get(f"/api/admin/training-jobs/{job_id}").get_json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(.05)
    assert job["status"] == "completed", job
    versions = client.get("/api/admin/model-versions?stage=intake").get_json()["items"]
    champion = next(x for x in versions if x["status"] == "champion")
    promoted = client.post(f"/api/admin/model-versions/{champion['id']}/promote", json={"reason": "test"}, headers={"X-CSRF-Token": token})
    assert promoted.status_code == 200 and promoted.get_json()["status"] == "implemented"
    rolled = client.post(f"/api/admin/model-versions/{champion['id']}/rollback", json={"reason": "test"}, headers={"X-CSRF-Token": token})
    assert rolled.status_code == 200
    assert client.get("/api/admin/audit").get_json()["items"]


def dataset_csv():
    return b"student_id;feature\nSTD-1;1\n"


def test_dataset_duplicate_edit_delete_and_training_lock(client):
    token = login(client)
    headers = {"X-CSRF-Token": token}
    first = client.post("/api/datasets", data={"stage": "intake", "file": (io.BytesIO(dataset_csv()), "one.csv")}, headers=headers)
    assert first.status_code == 201
    did = first.get_json()["id"]
    duplicate = client.post("/api/datasets", data={"stage": "intake", "file": (io.BytesIO(dataset_csv()), "copy.csv")}, headers=headers)
    assert duplicate.status_code == 409
    renamed = client.patch(f"/api/datasets/{did}", json={"name": "Dataset Utama.csv"}, headers=headers)
    assert renamed.status_code == 200 and renamed.get_json()["name"] == "Dataset Utama.csv"
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            c.execute("INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?)", ("busy-job", "intake", "running", 10, None, None, now()))
    locked = client.post(f"/api/datasets/{did}/train", json={}, headers=headers)
    assert locked.status_code == 409
    deleted = client.delete(f"/api/datasets/{did}", headers=headers)
    assert deleted.status_code == 200


def test_active_models_and_implement_endpoint(client):
    token = login(client)
    headers = {"X-CSRF-Token": token}
    active = client.get("/api/admin/models/active")
    assert active.status_code == 200
    assert {"intake", "academic_update"} <= set(active.get_json()["active"])
    candidate = next(x for x in client.get("/api/admin/model-versions").get_json()["items"] if x["status"] == "champion")
    implemented = client.post(f"/api/admin/model-versions/{candidate['id']}/implement", json={}, headers=headers)
    assert implemented.status_code == 200
    assert client.get("/api/admin/models/active").get_json()["active"][candidate["stage"]]["id"] == candidate["id"]


def test_delete_training_resets_dataset_and_removes_outputs(client):
    token = login(client); headers = {"X-CSRF-Token": token}
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            source = Path(__file__).parents[2] / "data.csv"
            c.execute("INSERT INTO datasets(id,name,stage,file_path,row_count,col_count,size_bytes,status,trained_at,uploaded_by,created_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("reset-dataset", "reset.csv", "academic_update", str(source), 4424, 37, source.stat().st_size, "trained", now(), 1, now(), "reset-checksum"))
            versions = [dict(x) for x in c.execute("SELECT id,algorithm,path FROM model_versions WHERE stage='academic_update'")]
            result = {"best": next(x['algorithm'] for x in versions if x['algorithm']=='random_forest'), "all_versions": {x['algorithm']: {"version": x['id'], "path": x['path']} for x in versions}}
            c.execute("INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?)", ("reset-job", "academic_update", "completed", 100, json.dumps(result), None, now()))
            dataset = c.execute("SELECT id,stage FROM datasets WHERE id='reset-dataset'").fetchone()
            job = c.execute("SELECT id,result FROM training_jobs WHERE id='reset-job'").fetchone()
    removed = client.delete(f"/api/admin/training-jobs/{job['id']}", headers=headers)
    assert removed.status_code == 200
    with client.application.app_context():
        from backend.app import db
        with db() as c:
            ds = c.execute("SELECT status,trained_at FROM datasets WHERE id=?", (dataset['id'],)).fetchone()
            assert tuple(ds) == ('ready', None)
            assert c.execute("SELECT count(*) FROM training_jobs WHERE id=?", (job['id'],)).fetchone()[0] == 0
            assert c.execute("SELECT count(*) FROM model_versions WHERE stage=?", (dataset['stage'],)).fetchone()[0] == 0
    assert dataset['stage'] not in client.get("/api/admin/models/active").get_json()["active"]


def test_recommended_model_can_be_implemented_without_active_file(client):
    token = login(client); headers = {"X-CSRF-Token": token}
    artifact = Path(client.application.config["ARTIFACT_DIR"])
    active = artifact / "active.json"
    if active.exists(): active.unlink()
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            c.execute("UPDATE model_versions SET status='candidate'")
            winner = c.execute("SELECT id,stage FROM model_versions ORDER BY created_at DESC LIMIT 1").fetchone()
            c.execute("UPDATE model_versions SET status='champion' WHERE id=?", (winner['id'],))
    implemented = client.post(f"/api/admin/model-versions/{winner['id']}/implement", json={}, headers=headers)
    assert implemented.status_code == 200
    assert implemented.get_json()["status"] == "implemented"
    assert json.loads(active.read_text())[winner["stage"]] == winner["id"]
    rows = client.get("/api/admin/model-versions").get_json()["items"]
    assert next(x for x in rows if x["id"] == winner["id"])["status"] == "champion"


def test_trained_dataset_can_be_deleted_without_deleting_models(client, tmp_path):
    token = login(client); headers = {"X-CSRF-Token": token}
    source = tmp_path / "demo.csv"
    source.write_bytes((Path(__file__).parents[2] / "data.csv").read_bytes())
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            c.execute("INSERT INTO datasets(id,name,stage,file_path,row_count,col_count,size_bytes,status,trained_at,uploaded_by,created_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("trained-delete", "demo.csv", "academic_update", str(source), 4424, 37, source.stat().st_size, "trained", now(), 1, now(), "demo-delete"))
            before = c.execute("SELECT count(*) FROM model_versions").fetchone()[0]
    deleted = client.delete("/api/datasets/trained-delete", headers=headers)
    assert deleted.status_code == 200
    with client.application.app_context():
        from backend.app import db
        with db() as c:
            assert c.execute("SELECT count(*) FROM datasets WHERE id='trained-delete'").fetchone()[0] == 0
            assert c.execute("SELECT count(*) FROM model_versions").fetchone()[0] == before


def test_model_comparison_edit_delete_and_active_protection(client):
    token = login(client)
    headers = {"X-CSRF-Token": token}
    models = client.get("/api/admin/model-versions").get_json()["items"]
    candidate = next(x for x in models if x["status"] != "champion")
    edited = client.patch(f"/api/admin/model-versions/{candidate['id']}", json={"name": "Model Pembanding A"}, headers=headers)
    assert edited.status_code == 200 and edited.get_json()["name"] == "Model Pembanding A"
    removed = client.delete(f"/api/admin/model-versions/{candidate['id']}", headers=headers)
    assert removed.status_code == 200
    assert candidate["id"] not in {x["id"] for x in client.get("/api/admin/model-versions").get_json()["items"]}
    champion = next(x for x in client.get("/api/admin/model-versions").get_json()["items"] if x["status"] == "champion")
    protected = client.delete(f"/api/admin/model-versions/{champion['id']}", headers=headers)
    assert protected.status_code == 409


def test_prediction_uses_implemented_model_stage_and_menu_order():
    source = (Path(__file__).parents[1] / "frontend/src/main.jsx").read_text()
    navigation = source[source.index('const navigation'):source.index('const stageName')]
    assert navigation.index('"students", "Mahasiswa"') < navigation.index('"batch", "Dataset"') < navigation.index('"models", "Model Center"')
    predict = source[source.index('function Predict('):source.index('function BatchPrediction')]
    assert 'useLoad("/admin/models/active")' in predict
    assert 'useState("academic_update")' in predict


def test_batch_prediction_ui_accepts_csv_xlsx_and_shows_prediction_probabilities():
    source = (Path(__file__).parents[1] / "frontend/src/main.jsx").read_text()
    batch = source[source.index("function BatchPrediction"):source.index("function Batch()")]
    assert 'accept=".csv,.xlsx' in batch
    assert 'await post(`/batch-jobs/${created.id}/run`)' in batch
    assert "Upload & Jalankan Prediksi" in batch
    assert "Status Struktur" not in batch
    assert "x.predicted_class" in batch
    assert "x.probabilities?.Dropout" in batch
    assert "x.probabilities?.Enrolled" in batch
    assert "x.probabilities?.Graduate" in batch


def test_management_ui_matches_requested_workflow():
    source = (Path(__file__).parents[1] / "frontend/src/main.jsx").read_text()
    assert 'function Reports()' not in source
    assert 'Promote' not in source
    assert '<Stage value={stage}' not in source[source.index('function Batch()'):source.index('function Models()')]
    models = source[source.index('function Models()'):source.index('function UsersAdmin()')]
    assert '<Stage value={stage}' not in models
    assert 'MAIN MODEL' in models and 'Main Model' in models
    assert 'PERBANDINGAN MODEL' in models and 'Perbandingan Model' in models
    assert 'stageName(key)' not in models
    assert 'm.stage === "intake"' not in models
    assert 'Champion hasil training' in models
    assert 'Implementasikan' in models
    assert 'Champion berhasil diimplementasikan sebagai Main Model.' in models
    assert 'Hapus Training' in models
    batch = source[source.index('function Batch()'):source.index('function Models()')]
    assert '>Edit<' in batch and '>Delete<' in batch


def valid_training_csv():
    source = Path(__file__).parents[2] / "data.csv"
    return source.read_bytes()


def test_preprocessing_report_component_is_defined():
    source = (Path(__file__).parents[1] / "frontend/src/main.jsx").read_text()
    assert "function Metric(" in source
    assert 'id="preprocessing-result"' in source


def test_preprocessing_preserves_trained_dataset_status(client):
    token = login(client); headers = {"X-CSRF-Token": token}
    source = Path(__file__).parents[1] / "data/datasets/e5ccd8a8-880e-4303-9053-b0ccac713d18.csv"
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            c.execute("INSERT INTO datasets(id,name,stage,file_path,row_count,col_count,size_bytes,status,trained_at,uploaded_by,created_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("trained-preprocess", "trained.csv", "academic_update", str(source), 4424, 37, source.stat().st_size, "trained", now(), 1, now(), "trained-preprocess-checksum"))
    result = client.post("/api/datasets/trained-preprocess/preprocess", json={}, headers=headers)
    assert result.status_code == 200
    assert result.get_json()["status"] == "trained"
    with client.application.app_context():
        from backend.app import db
        with db() as c:
            assert c.execute("SELECT status FROM datasets WHERE id='trained-preprocess'").fetchone()[0] == "trained"


def test_dataset_preprocess_preview_and_one_successful_training(client):
    token = login(client); headers = {"X-CSRF-Token": token}
    uploaded = client.post("/api/datasets", data={"file": (io.BytesIO(valid_training_csv()), "training.csv")}, headers=headers)
    assert uploaded.status_code == 201
    did = uploaded.get_json()["id"]
    preview = client.get(f"/api/datasets/{did}")
    assert preview.status_code == 200 and preview.get_json()["rows"]
    checked = client.post(f"/api/datasets/{did}/preprocess", json={}, headers=headers)
    assert checked.status_code == 200
    report = checked.get_json()["preprocessing"]
    assert {"null_cells", "invalid_cells", "duplicate_rows", "class_distribution", "ready"} <= set(report)
    assert checked.get_json()["status"] == "ready"
    with client.application.app_context():
        from backend.app import db, now
        with db() as c:
            c.execute("UPDATE datasets SET status='trained',trained_at=? WHERE id=?", (now(), did))
    duplicate_training = client.post(f"/api/datasets/{did}/train", json={}, headers=headers)
    assert duplicate_training.status_code == 409


def test_fresh_install_has_no_model_and_prediction_is_locked(tmp_path):
    fresh = create_app({"TESTING": True, "DATABASE": str(tmp_path / "fresh.sqlite"), "ARTIFACT_DIR": str(tmp_path / "fresh-artifacts"), "CREDENTIALS_FILE": str(tmp_path / "fresh-credentials.txt"), "SECRET_KEY": "test-secret", "DATASET": str(Path(__file__).parents[2] / "data.csv")})
    client = fresh.test_client(); token = login(client); headers = {"X-CSRF-Token": token}
    active = client.get("/api/admin/models/active")
    assert active.status_code == 200 and active.get_json()["active"] == {}
    assert client.get("/api/model-schemas/intake/active").status_code == 409
    blocked = client.post("/api/predictions", json={"student_id": "STD-1", "stage": "intake"}, headers=headers)
    assert blocked.status_code == 409


def test_clean_ready_dataset_has_no_comparison_until_training(client):
    token = login(client); headers = {"X-CSRF-Token": token}
    with client.application.app_context():
        from backend.app import db
        with db() as c:
            c.execute("DELETE FROM model_versions")
            c.execute("DELETE FROM training_jobs")
            c.execute("INSERT INTO datasets(id,name,stage,file_path,row_count,col_count,size_bytes,status,trained_at,uploaded_by,created_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("ready-1", "ready.csv", "academic_update", str(Path(__file__).parents[2] / "data.csv"), 4424, 37, 1, "ready", None, 1, "2026-09-29", "unique-ready"))
    assert client.get("/api/admin/model-versions").get_json()["items"] == []
    assert client.get("/api/admin/training-jobs").get_json()["items"] == []
    ready = client.get("/api/datasets").get_json()["items"]
    assert any(x["id"] == "ready-1" and x["status"] == "ready" and x["trained_at"] is None for x in ready)


def test_training_lives_only_in_model_center_ui():
    source = (Path(__file__).parents[1] / "frontend/src/main.jsx").read_text()
    dataset = source[source.index("function Batch()"):source.index("function Models()")]
    models = source[source.index("function Models()"):source.index("function UsersAdmin()")]
    assert 'Dataset & Training' not in source
    assert '>Training<' not in dataset and '/train`' not in dataset
    assert 'Preprocessing' in dataset and '>View<' in dataset and '>Edit<' in dataset and '>Delete<' in dataset
    assert 'Pilih dataset' in models and '>Training<' in models


def test_frontend_spa_served(client):
    assert b'<div id="root">' in client.get("/").data
    assert client.get("/does/not/exist").status_code == 200


def test_feature_stage_counts():
    assert len(INTAKE_FEATURES) == 24
    assert len(UPDATE_FEATURES) == 36
    assert not any("Curricular" in x for x in INTAKE_FEATURES)


def test_credentials_are_private(app):
    assert os.stat(app.config["CREDENTIALS_FILE"]).st_mode & 0o777 == 0o600
