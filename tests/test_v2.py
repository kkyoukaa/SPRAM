"""Uji v2: kamus bahasa Indonesia, sistem pakar, akses, dan alur tindak lanjut."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend import expert
from backend.app import create_app
from backend.dictionary import kamus, terjemahkan
from backend.ml import UPDATE_FEATURES

ROOT = Path(__file__).parents[1]
TINGGI = {
    "Debtor": 1, "Tuition fees up to date": 0, "Scholarship holder": 0, "Displaced": 1,
    "Application order": 9, "Daytime/evening attendance": 0, "Age at enrollment": 35, "Gender": 1,
    "Course": 9119, "Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 1,
    "Curricular units 1st sem (grade)": 8, "Curricular units 2nd sem (enrolled)": 6,
    "Curricular units 2nd sem (approved)": 0, "Curricular units 2nd sem (grade)": 7,
}


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v2")
    return create_app({"TESTING": True, "BOOTSTRAP_MODELS": False,
                       "DATABASE": str(tmp / "v2.sqlite"), "CREDENTIALS_FILE": str(tmp / "creds.txt"),
                       "ARTIFACT_DIR": str(ROOT / "artifacts"), "SECRET_KEY": "test",
                       "DATASET": str(ROOT.parent / "data.csv")})


@pytest.fixture(scope="module")
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
    response = client.post("/api/auth/login", json={"email": email, "password": password},
                           headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["csrf_token"]


def fitur_contoh(client):
    schema = client.get("/api/model-schemas/academic_update/active").get_json()
    return {f["name"]: (f["categories"][0]["value"] if f.get("categories") else f["min"]) for f in schema["features"]}


def prediksi(client, headers, sid="STD-0001", tanggal="2026-02-01"):
    nilai = {**fitur_contoh(client), **TINGGI}
    return client.post("/api/predictions", headers=headers,
                       json={"student_id": sid, "stage": "academic_update", "snapshot_date": tanggal,
                             "features": nilai})


def test_kamus_lengkap_dan_tidak_bocor_istilah_inggris():
    k = kamus()["features"]
    assert set(k) == set(UPDATE_FEATURES)
    for nama, entry in k.items():
        assert entry["label"] and entry["label"] != nama
        assert entry["group"] and entry["factor_type"] in ("dapat_ditindaklanjuti", "konteks", "sensitif")
        if entry.get("values"):
            for kode in entry["values"]:
                assert not terjemahkan(nama, kode).startswith("Kode ")
    assert terjemahkan("Course", 9119) == "Teknik Informatika"
    assert terjemahkan("Course", 123456) == "Kode 123456 (belum terdaftar)"
    assert terjemahkan("Debtor", 1) == "Ya"


def test_aturan_r01_aktif_dan_r08_hanya_fallback():
    fitur = {**{f: 0 for f in UPDATE_FEATURES}, **TINGGI}
    drivers = [{"feature": "Debtor", "shap": 0.2, "direction": "increase"}]
    aktif = expert.aturan_aktif(fitur, drivers, "high", expert.DEFAULT_RULES)
    ids = [r["rule_id"] for r in aktif]
    assert "R01" in ids and "R08" not in ids
    assert any("tunggakan" in a.lower() for a in aktif[0]["alasan"])

    aman = {f: 0 for f in UPDATE_FEATURES}
    aman.update({"Curricular units 1st sem (enrolled)": 6, "Curricular units 1st sem (approved)": 6,
                 "Curricular units 2nd sem (enrolled)": 6, "Curricular units 2nd sem (approved)": 6,
                 "Curricular units 1st sem (grade)": 15, "Curricular units 2nd sem (grade)": 15,
                 "Curricular units 1st sem (evaluations)": 6, "Curricular units 2nd sem (evaluations)": 6,
                 "Tuition fees up to date": 1, "Scholarship holder": 1, "Application order": 0,
                 "Daytime/evening attendance": 1, "Age at enrollment": 19})
    fallback = expert.aturan_aktif(aman, [], "high", expert.DEFAULT_RULES)
    assert [r["rule_id"] for r in fallback] == ["R08"]


def test_aturan_sensitif_dan_makro_ditolak():
    for nama in ("Gender", "Nacionality", "GDP"):
        galat = expert.validasi_rule({"rule_id": "RX", "nama": "uji", "hipotesis": "x", "pertanyaan": "y",
                                      "kondisi": [{"fitur": nama, "op": "==", "nilai": 1}]}, set(UPDATE_FEATURES))
        assert galat and "tidak boleh" in galat[0]
    assert expert.validasi_rule({"rule_id": "RX", "nama": "uji", "hipotesis": "x", "pertanyaan": "y",
                                 "kondisi": [{"fitur": "Bukan Fitur", "op": "==", "nilai": 1}]}, set(UPDATE_FEATURES))


def test_detail_bahasa_indonesia_dan_profil_lengkap(client):
    headers = {"X-CSRF-Token": login(client)}
    assert prediksi(client, headers).status_code == 201
    data = client.get("/api/students/STD-0001/detail").get_json()
    assert data["prediction"]["class_label"] in ("Putus kuliah", "Masih aktif", "Lulus")
    assert len(data["profile"]) == 36
    kalimat = [x["sentence"] for x in data["factors"]["increase"] + data["factors"]["decrease"] + data["factors"]["background"]]
    assert kalimat, "faktor harus tersedia"
    for teks in kalimat:
        for nama in UPDATE_FEATURES:
            assert nama not in teks
    for baris in data["profile"]:
        assert baris["label"] != baris["feature"]
        assert not baris["value_label"].startswith("Kode ")
    assert data["consultation"]["active_rules"]
    assert data["statuses"]["belum"] == "Belum ditangani"


def test_alur_konsultasi_dan_tindak_lanjut(client):
    headers = {"X-CSRF-Token": login(client)}
    preview = client.post("/api/consultations/preview", headers=headers,
                          json={"student_id": "STD-0001", "jawaban": {"R01": "ya"}})
    assert preview.status_code == 200
    body = preview.get_json()
    assert body["rekomendasi"][0]["rule_id"] == "R01"
    assert body["rekomendasi"][0]["tindakan"]
    assert any("keuangan" in t.lower() for t in body["rekomendasi"][0]["tindakan"])

    # penanganan dan tindakan adalah wewenang dosen wali, bukan admin
    dosen = next(u for u in client.get("/api/admin/users").get_json()["items"] if u["email"] == "yanto@spram.local")
    tetapkan = client.post("/api/admin/assignments", headers=headers,
                           json={"advisor_id": dosen["id"], "student_ids": ["STD-0001"]})
    assert tetapkan.status_code in (201, 409), tetapkan.get_json()
    adv = {"X-CSRF-Token": login(client, "yanto@spram.local")}

    saved = client.post("/api/consultations", headers=adv,
                        json={"student_id": "STD-0001", "jawaban": {"R01": "ya"}})
    assert saved.status_code == 201 and saved.get_json()["aturan_aktif"]

    kasus = client.post("/api/cases", headers=adv,
                        json={"student_id": "STD-0001", "status": "dipantau", "tindakan": "Rujuk keuangan",
                              "catatan": "Sudah dihubungi"})
    assert kasus.status_code == 201 and kasus.get_json()["status_label"] == "Dipantau"
    login(client)
    ringkas = client.get("/api/dashboard/summary").get_json()
    assert ringkas["monitored_count"] == 1 and ringkas["untreated_count"] == 0
    assert {x["student_id"] for x in ringkas["high_risk_monitored"]} == {"STD-0001"}

    risiko = client.get("/api/students/STD-0001/detail").get_json()["prediction"]["risk_band"]
    assert risiko == "high", "status penanganan tidak boleh mengubah risiko"


def test_admin_tidak_bisa_menangani_kasus(client):
    """Admin hanya memantau: penanganan ditolak, data mahasiswa tetap bisa diedit."""
    headers = {"X-CSRF-Token": login(client)}
    kasus = client.post("/api/cases", headers=headers,
                        json={"student_id": "STD-0001", "status": "dipantau", "tindakan": "x", "catatan": "y"})
    assert kasus.status_code == 403 and "dosen wali" in kasus.get_json()["error"].lower()
    assert client.post("/api/consultations", headers=headers,
                       json={"student_id": "STD-0001", "jawaban": {"R01": "ya"}}).status_code == 403
    assert client.post("/api/interventions", headers=headers,
                       json={"student_id": "STD-0001", "type": "academic"}).status_code == 403
    ubah = client.patch("/api/students/STD-0001", headers=headers, json={"cohort": "2026"})
    assert ubah.status_code == 200


def test_prediksi_baru_membuka_kembali_kasus(client):
    headers = {"X-CSRF-Token": login(client)}
    assert prediksi(client, headers, tanggal="2026-08-01").status_code == 201
    data = client.get("/api/students/STD-0001/detail").get_json()
    assert data["case"]["status"] == "belum"
    assert any("Dibuka kembali" in (e["catatan"] or "") for e in data["events"])


def test_dosen_hanya_melihat_bimbingannya(client):
    headers = {"X-CSRF-Token": login(client)}
    buat = client.post("/api/admin/users", headers=headers,
                       json={"name": "Dosen Lain", "email": "dosen2@spram.local", "password": "rahasia-panjang-1", "role": "advisor"})
    assert buat.status_code == 201
    # seed tidak lagi auto-assign: admin harus menetapkan sendiri
    yanto = next(u for u in client.get("/api/admin/users").get_json()["items"] if u["email"] == "yanto@spram.local")
    tetapkan = client.post("/api/admin/assignments", headers=headers,
                           json={"advisor_id": yanto["id"], "student_ids": ["STD-0001"]})
    assert tetapkan.status_code in (201, 409), tetapkan.get_json()
    asing = client.post("/api/predictions", headers=headers,
                        json={"student_id": "STD-0002", "stage": "academic_update", "snapshot_date": "2026-02-01",
                              "features": {**fitur_contoh(client), **TINGGI}})
    assert asing.status_code == 201
    login(client, "yanto@spram.local")
    assert client.get("/api/students/STD-0001/detail").status_code == 200
    assert client.get("/api/students/STD-0002/detail").status_code == 403
    assert client.get("/api/rules").status_code == 403
    daftar = client.get("/api/students").get_json()["items"]
    assert {x["student_id"] for x in daftar} == {"STD-0001"}


def test_admin_assign_mengubah_lingkup_dosen(client):
    headers = {"X-CSRF-Token": login(client)}
    dosen = next(u for u in client.get("/api/admin/users").get_json()["items"] if u["email"] == "dosen2@spram.local")
    r = client.post("/api/admin/assignments", headers=headers,
                    json={"advisor_id": dosen["id"], "student_ids": ["STD-0002"]})
    assert r.status_code == 201 and r.get_json()["count"] == 1
    login(client, "dosen2@spram.local", "rahasia-panjang-1")
    assert client.get("/api/students/STD-0002/detail").status_code == 200
    assert client.get("/api/students/STD-0001/detail").status_code == 403


def test_admin_dapat_mengelola_aturan(client):
    headers = {"X-CSRF-Token": login(client)}
    assert client.get("/api/rules").get_json()["items"]
    ditolak = client.post("/api/rules", headers=headers,
                          json={"rule_id": "R90", "nama": "Bias", "hipotesis": "x", "pertanyaan": "y",
                                "kondisi": [{"fitur": "Gender", "op": "==", "nilai": 1}], "tindakan": {}})
    assert ditolak.status_code == 422 and "sensitif" in ditolak.get_json()["error"]
    dibuat = client.post("/api/rules", headers=headers,
                         json={"rule_id": "R91", "nama": "Uji aturan", "hipotesis": "Kemungkinan uji",
                               "pertanyaan": "Apakah uji?", "prioritas": 20,
                               "kondisi": [{"fitur": "Displaced", "op": "==", "nilai": 0}],
                               "tindakan": {"ya": ["Tindak lanjut uji"], "tidak": [], "belum_tahu": []}})
    assert dibuat.status_code == 201
    assert client.delete("/api/rules/R91", headers=headers).status_code == 200
    assert next(r for r in client.get("/api/rules").get_json()["items"] if r["rule_id"] == "R91")["aktif"] == 0


def test_kalimat_tidak_menyesatkan_saat_nol_unit_diambil():
    from backend.dictionary import kalimat
    nilai = {"Curricular units 2nd sem (approved)": 0, "Curricular units 2nd sem (enrolled)": 0}
    hasil = kalimat("Curricular units 2nd sem (approved)", 0, "naik", nilai)
    assert "dari 0" not in hasil
    assert "tidak ada unit diambil" in hasil
    nilai2 = {"Curricular units 2nd sem (approved)": 1, "Curricular units 2nd sem (enrolled)": 6}
    assert "1 dari 6" in kalimat("Curricular units 2nd sem (approved)", 1, "naik", nilai2)
