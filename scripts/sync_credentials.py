#!/usr/bin/env python3
"""Sync demo credentials file with DB password hashes.

File format (pasangan baris, urutan bebas):
    Admin: admin@spram.local
    Password: <pw-admin>
    Advisor: yanto@spram.local  (Yanto S.pd., M.pd.)
    Password: <pw-advisor>

Setiap akun punya password sendiri. Script ini menulis ulang hash dari
password yang tercantum di file, lalu memverifikasinya.
"""
import re
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).parents[1]
cred = ROOT / "data" / "demo-credentials.txt"
db_path = ROOT / "data" / "spram.sqlite"

lines = cred.read_text().splitlines()
pairs = {}
pending = None
for raw in lines:
    line = raw.strip()
    if not line:
        continue
    if line.lower().startswith("password:"):
        if pending is None:
            raise SystemExit(f"Password tanpa akun di atasnya: {line!r}")
        pairs[pending] = line.split(":", 1)[1].strip()
        pending = None
        continue
    m = re.search(r"[\w.+-]+@[\w.-]+", line)
    if not m:
        raise SystemExit(f"Baris tidak dikenali (butuh email): {line!r}")
    pending = m.group(0).lower()

if not pairs:
    raise SystemExit("Tidak ada pasangan email/password di file credentials")

conn = sqlite3.connect(str(db_path))
try:
    for email, pw in pairs.items():
        row = conn.execute(
            "SELECT id FROM users WHERE email=?", (email,)
        ).fetchone()
        if not row:
            print(f"SKIP  {email}: tidak ada di tabel users")
            continue
        conn.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (generate_password_hash(pw), email),
        )
        print(f"SET   {email} (id {row[0]})")
    conn.commit()

    bad = []
    for email, pw in pairs.items():
        row = conn.execute(
            "SELECT password_hash FROM users WHERE email=?", (email,)
        ).fetchone()
        if not row:
            continue
        ok = check_password_hash(row[0], pw)
        print(f"CHECK {email}: match={ok}")
        if not ok:
            bad.append(email)
finally:
    conn.close()

if bad:
    raise SystemExit(f"Hash mismatch: {bad}")
print("DONE: credentials synced")
