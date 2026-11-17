import csv, hashlib, io, json, os, secrets, sqlite3, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps, lru_cache

import joblib
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from .ml import train_stage, risk_band, explain, CLASSES

ROOT=Path(__file__).parents[1]

def now(): return datetime.now(timezone.utc).isoformat()
def db():
 c=sqlite3.connect(current_app.config['DATABASE']);c.row_factory=sqlite3.Row;return c
from flask import current_app

def init_db(app):
 Path(app.config['DATABASE']).parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(app.config['DATABASE']) as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password_hash TEXT,role TEXT,status TEXT DEFAULT 'active');
  CREATE TABLE IF NOT EXISTS students(student_id TEXT PRIMARY KEY,cohort TEXT,program_code TEXT,active_status TEXT DEFAULT 'active');
  CREATE TABLE IF NOT EXISTS assignments(advisor_id INTEGER,student_id TEXT,UNIQUE(advisor_id,student_id));
  CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,student_id TEXT,stage TEXT,snapshot_date TEXT,features TEXT,probabilities TEXT,predicted_class TEXT,risk_band TEXT,model_version TEXT,schema_version TEXT,drivers TEXT,protectors TEXT,idempotency_key TEXT UNIQUE,created_at TEXT);
  CREATE TABLE IF NOT EXISTS interventions(id TEXT PRIMARY KEY,student_id TEXT,prediction_id TEXT,type TEXT,note TEXT,due_date TEXT,status TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS batch_jobs(id TEXT PRIMARY KEY,owner INTEGER,stage TEXT,status TEXT,valid_count INTEGER,invalid_count INTEGER,valid_rows TEXT,errors TEXT,results TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS model_versions(id TEXT PRIMARY KEY,stage TEXT,algorithm TEXT,status TEXT,experimental INTEGER,metrics TEXT,path TEXT,checksum TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS training_jobs(id TEXT PRIMARY KEY,stage TEXT,status TEXT,progress INTEGER,result TEXT,error TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS audits(id INTEGER PRIMARY KEY AUTOINCREMENT,actor INTEGER,action TEXT,resource TEXT,resource_id TEXT,outcome TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
  CREATE TABLE IF NOT EXISTS reference_labels(feature TEXT,code TEXT,label TEXT,UNIQUE(feature,code));
  CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,name TEXT,stage TEXT,file_path TEXT,row_count INTEGER,col_count INTEGER,size_bytes INTEGER,status TEXT DEFAULT 'uploaded',trained_at TEXT,uploaded_by INTEGER,created_at TEXT,checksum TEXT);
  CREATE TABLE IF NOT EXISTS rules(rule_id TEXT PRIMARY KEY,nama TEXT,kondisi_json TEXT,hipotesis TEXT,pertanyaan TEXT,tindakan_json TEXT,prioritas INTEGER,aktif INTEGER DEFAULT 1,topik TEXT DEFAULT 'umum',updated_by INTEGER,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS consultations(consult_id TEXT PRIMARY KEY,student_id TEXT,prediction_id TEXT,advisor_id INTEGER,jawaban_json TEXT,aturan_aktif_json TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY,student_id TEXT UNIQUE,status TEXT,tindakan TEXT,catatan TEXT,updated_by INTEGER,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS case_events(event_id TEXT PRIMARY KEY,case_id TEXT,status_lama TEXT,status_baru TEXT,catatan TEXT,timestamp TEXT);
  CREATE TABLE IF NOT EXISTS llm_providers(id TEXT PRIMARY KEY,name TEXT,base_url TEXT,api_key_enc TEXT,models_json TEXT,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS llm_config(id INTEGER PRIMARY KEY CHECK (id=1),provider_id TEXT,model TEXT,updated_by INTEGER,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS chat_sessions(id TEXT PRIMARY KEY,advisor_id INTEGER,student_id TEXT,title TEXT DEFAULT 'Percakapan baru',created_at TEXT,updated_at TEXT);
  CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,role TEXT,content TEXT,created_at TEXT);
  CREATE TABLE IF NOT EXISTS chat_cache(cache_key TEXT PRIMARY KEY,answer TEXT,mode TEXT,hits INTEGER DEFAULT 0,created_at TEXT,last_hit TEXT);''')
  if not c.execute('SELECT 1 FROM rules').fetchone():
   from .expert import DEFAULT_RULES
   for r in DEFAULT_RULES:
    c.execute('INSERT INTO rules(rule_id,nama,kondisi_json,hipotesis,pertanyaan,tindakan_json,prioritas,aktif,topik,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (r['rule_id'],r['nama'],json.dumps({'dan':r.get('kondisi',[]),'atau':r.get('kondisi_atau',[]),'fallback':r.get('fallback',False)}),
               r['hipotesis'],r['pertanyaan'],json.dumps(r['tindakan']),r['prioritas'],1,r.get('topik','umum'),now()))
  try:c.execute('ALTER TABLE datasets ADD COLUMN checksum TEXT')
  except sqlite3.OperationalError:pass
  try:c.execute('ALTER TABLE model_versions ADD COLUMN name TEXT')
  except sqlite3.OperationalError:pass
  try:c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_student ON assignments(student_id)')
  except sqlite3.IntegrityError as e:print(f'PERINGATAN: assignments berisi mahasiswa ganda, indeks unik tidak dibuat: {e}')
  cred=Path(app.config['CREDENTIALS_FILE']);cred.parent.mkdir(parents=True,exist_ok=True)
  if not c.execute('SELECT 1 FROM users').fetchone():
   akun=[('Admin SPRAM','admin@spram.local','admin'),('Dosen Wali Demo','yanto@spram.local','advisor')]
   pw={email:secrets.token_urlsafe(18) for _,email,_ in akun}
   for name,email,role in akun: c.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',(name,email,generate_password_hash(pw[email]),role))
   c.executemany('INSERT INTO students(student_id,cohort,program_code) VALUES(?,?,?)',[('STD-0001','2026','TI'),('STD-0002','2026','SI')])
   # Tanpa penugasan awal: mahasiswa harus ditetapkan manual oleh admin.
   cred.write_text(f'Admin: admin@spram.local\nPassword: {pw["admin@spram.local"]}\nAdvisor: yanto@spram.local\nPassword: {pw["yanto@spram.local"]}\n');os.chmod(cred,0o600)
  c.execute("INSERT OR IGNORE INTO settings VALUES('thresholds',?)",(json.dumps({'version':'risk-v1','medium':.4,'high':.7}),))

def bootstrap_models(app):
 root=Path(app.config['ARTIFACT_DIR']);root.mkdir(parents=True,exist_ok=True); active=root/'active.json'
 if active.exists(): return
 values={}
 for stage in ('intake','academic_update'):
  result=train_stage(app.config['DATASET'],stage,root,quick=True)
  best=result['best']
  values[stage]=result['all_versions'][best]['version']
  with sqlite3.connect(app.config['DATABASE']) as c:
   for alg,v in result['all_versions'].items():
    m=v['metrics'];status='champion' if alg==best else 'candidate'
    experimental=not (m['recall_dropout']>=.7 and m['ece']<=.1)
    c.execute('INSERT OR REPLACE INTO model_versions(id,stage,algorithm,status,experimental,metrics,path,checksum,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(v['version'],stage,alg,status,experimental,json.dumps({'test':m,'candidates':result['metrics']['candidates']}),v['path'],v['checksum'],now()))
 active.write_text(json.dumps(values))

def audit(action,resource,rid='',outcome='success'):
 with db() as c:c.execute('INSERT INTO audits(actor,action,resource,resource_id,outcome,created_at) VALUES(?,?,?,?,?,?)',(session.get('uid'),action,resource,str(rid),outcome,now()))
def user():
 if not session.get('uid'): return None
 with db() as c:return c.execute('SELECT id,name,email,role,status FROM users WHERE id=?',(session['uid'],)).fetchone()
def auth(fn):
 @wraps(fn)
 def w(*a,**k):
  if not user(): return jsonify(error='Unauthenticated'),401
  return fn(*a,**k)
 return w
def admin(fn):
 @wraps(fn)
 def w(*a,**k):
  u=user()
  if not u:return jsonify(error='Unauthenticated'),401
  if u['role']!='admin':return jsonify(error='Forbidden'),403
  return fn(*a,**k)
 return w
def advisor_only(fn):
 """Penanganan & tindakan adalah wewenang dosen wali. Admin hanya memantau."""
 @wraps(fn)
 def w(*a,**k):
  u=user()
  if not u:return jsonify(error='Unauthenticated'),401
  if u['role']!='advisor':return jsonify(error='Penanganan dan tindakan hanya dapat dilakukan oleh dosen wali. Admin hanya memantau status dan data mahasiswa.'),403
  return fn(*a,**k)
 return w
def allowed(student_id):
 u=user()
 if u and u['role']=='admin':return True
 with db() as c:return bool(u and c.execute('SELECT 1 FROM assignments WHERE advisor_id=? AND student_id=?',(u['id'],student_id)).fetchone())
def model_data(stage):
 active=Path(current_app.config['ARTIFACT_DIR'])/'active.json'
 if not active.exists(): raise LookupError('Belum ada Main Model yang diimplementasikan')
 version=json.loads(active.read_text()).get(stage)
 if not version: raise LookupError('Belum ada Main Model yang diimplementasikan')
 path=Path(current_app.config['ARTIFACT_DIR'])/version
 return version,path,joblib.load(path/'pipeline.joblib'),json.loads((path/'feature_schema.json').read_text())
def serialize_prediction(row):
 d=dict(row);d['probabilities']=json.loads(d['probabilities']);d['features']=json.loads(d['features']);d['top_drivers']=json.loads(d['drivers']);d['top_protectors']=json.loads(d['protectors']);d['prediction_id']=d['id'];d['disclaimer']='Kontribusi model bukan bukti sebab-akibat.';return d
def formula(v):
 s=str(v);return "'"+s if s[:1] in '=+-@' else s

STATUS_PENANGANAN={'belum':'Belum ditangani','dijadwalkan':'Dijadwalkan','konseling':'Sudah konseling','dipantau':'Dipantau','selesai':'Penanganan selesai'}
STATUS_URUT=list(STATUS_PENANGANAN)
MAX_BIMBINGAN=5

def fitur_names():
 try:return {f['name'] for f in model_data('academic_update')[3]['features']}
 except LookupError:return set()

def chat_scope_db():
 """Batasan percakapan yang diatur admin di panel Aturan (sejalur dengan basis aturan)."""
 from .advisor_chat import DEFAULT_SCOPE
 with db() as c:row=c.execute("SELECT value FROM settings WHERE key='chat_scope'").fetchone()
 if not row:return dict(DEFAULT_SCOPE)
 try:data=json.loads(row['value'])
 except (json.JSONDecodeError,TypeError):return dict(DEFAULT_SCOPE)
 return {**DEFAULT_SCOPE,**{k:v for k,v in data.items() if k in DEFAULT_SCOPE or k=='aktif'}}

def aturan_db(aktif_saja=False):
 with db() as c:rows=c.execute('SELECT * FROM rules'+(' WHERE aktif=1' if aktif_saja else '')+' ORDER BY prioritas,rule_id').fetchall()
 out=[]
 for r in rows:
  d=dict(r);k=json.loads(d.pop('kondisi_json') or '{}');d['kondisi']=k.get('dan',[]);d['kondisi_atau']=k.get('atau',[]);d['fallback']=k.get('fallback',False)
  d['tindakan']=json.loads(d.pop('tindakan_json') or '{}');d['aktif']=int(d['aktif']);out.append(d)
 return out

def _label(nama):
 from .dictionary import label
 try:return label(nama)
 except KeyError:return nama

BAND_TEKS={'high':'tinggi','medium':'sedang','low':'rendah'}
STAGE_TEKS={'intake':'data penerimaan','academic_update':'pembaruan akademik'}

def tebak_intent(teks):
 t=(teks or '').lower()
 if any(k in t for k in ('risiko','tinggi','mengapa','kenapa','faktor','sebab')):return 'why'
 if any(k in t for k in ('saran','intervensi','tindak','rekomendasi','lakukan','bantu')):return 'intervention'
 if any(k in t for k in ('berubah','ubah','banding','sebelumnya','tren')):return 'changes'
 if any(k in t for k in ('yakin','akurat','percaya','probabilit','peluang')):return 'confidence'
 if any(k in t for k in ('data','profil','fitur','dipakai')):return 'profile'
 return None

def jawab_asisten(row,intent):
 """Jawaban asisten dalam bahasa Indonesia, memakai kamus terpusat."""
 from .dictionary import label_kelas,terjemahkan
 probs=json.loads(row['probabilities']);p_do=probs.get('Dropout',0)
 drivers=json.loads(row['drivers']);band=BAND_TEKS.get(row['risk_band'],row['risk_band'])
 fitur=json.loads(row['features'])
 if intent=='why':
  top=', '.join(_label(d['feature']) for d in drivers[:3]) if drivers else 'tidak tersedia'
  return (f'Peluang putus kuliah menurut model: {p_do:.1%} (risiko {band}). '
          f'Faktor yang paling mempengaruhi: {top}. Ini hubungan di dalam model, bukan bukti sebab-akibat.')
 if intent=='intervention':
  saran=[]
  for d in drivers[:3]:
   f=d['feature'].lower()
   if 'tuition' in f or 'debtor' in f:saran.append('Periksa kendala administrasi keuangan')
   elif 'credited' in f or 'approved' in f or 'enrolled' in f or 'grade' in f:saran.append('Tinjau beban dan pencapaian akademik')
   elif 'age' in f or 'gender' in f or 'marital' in f:saran.append('Pertimbangkan dukungan nonakademik')
   else:saran.append(f'Tinjau faktor: {_label(d["feature"])}')
  if not saran:saran=['Konfirmasi konteks akademik dan administrasi bersama mahasiswa']
  return ('Saran tindak lanjut (nonpunitif): '+'; '.join(dict.fromkeys(saran))+
          '. Mohon konfirmasi konteks langsung dengan mahasiswa sebelum menentukan tindakan.')
 if intent=='changes':
  with db() as c:prev=c.execute('SELECT * FROM predictions WHERE student_id=? AND id!=? ORDER BY created_at DESC LIMIT 1',(row['student_id'],row['id'])).fetchone()
  if not prev:return ('Belum ada pencatatan sebelumnya untuk dibandingkan, jadi perubahan peluang belum bisa dihitung. '
                      f'Peluang putus kuliah saat ini {p_do:.1%} (risiko {band}).')
  pp=json.loads(prev['probabilities']);delta=p_do-pp.get('Dropout',0)
  arah='naik' if delta>0 else ('turun' if delta<0 else 'tidak berubah')
  return (f'Dibanding pencatatan sebelumnya, peluang putus kuliah {arah} '
          f'{abs(delta):.1%} (dari {pp.get("Dropout",0):.1%} menjadi {p_do:.1%}). '
          f'Tahap sebelumnya: {STAGE_TEKS.get(prev["stage"],prev["stage"])}, '
          f'tahap saat ini: {STAGE_TEKS.get(row["stage"],row["stage"])}.')
 if intent=='confidence':
  vals=sorted(probs.items(),key=lambda x:-x[1]);margin=vals[0][1]-vals[1][1] if len(vals)>1 else 1
  yakin='tinggi' if margin>.2 else ('moderat' if margin>.05 else 'rendah')
  rincian=', '.join(f'{label_kelas(k)} {v:.1%}' for k,v in vals)
  return (f'Peluang tiap kelas: {rincian}. Selisih dua kelas teratas {margin:.1%} '
          f'(keyakinan {yakin}). Tahap data: {STAGE_TEKS.get(row["stage"],row["stage"])}. '
          f'Rincian versi model tercatat pada riwayat prediksi.')
 if intent=='profile':
  dipakai=[_label(nama) for nama in fitur]
  return (f'Model memakai {len(dipakai)} fitur dari data {STAGE_TEKS.get(row["stage"],row["stage"])}, '
          f'antara lain: {", ".join(dipakai[:8])}, dan seterusnya. '
          f'Nama dan angkatan tidak dipakai karena bukan bagian dari fitur model.')
 return 'Pertanyaan ini belum didukung asisten. Silakan pilih pertanyaan yang tersedia atau hubungi bagian akademik.'

def _rekomendasi_siswa(row,jawaban=None):
 from .expert import aturan_aktif,kontribusi,rekomendasi,thresholds as ambang_aturan
 fitur,drivers,_=jelaskan(row)
 aktif=aturan_aktif(fitur,drivers,row['risk_band'],aturan_db(aktif_saja=True),ambang_aturan())
 for r in aktif:r['kontribusi']=kontribusi(r,drivers)
 aktif.sort(key=lambda r:(r.get('prioritas',99),-r['kontribusi']))
 return rekomendasi(aktif,jawaban or {},row['risk_band'],drivers)

def prediksi_terakhir(sid):
 with db() as c:r=c.execute('SELECT * FROM predictions WHERE student_id=? ORDER BY created_at DESC LIMIT 1',(sid,)).fetchone()
 return r

@lru_cache(maxsize=6)
def _artefak(path):
 """Pipeline + daftar fitur dimuat sekali per versi model (artefak tidak berubah)."""
 p=Path(path)
 return joblib.load(p/'pipeline.joblib'),[f['name'] for f in json.loads((p/'feature_schema.json').read_text())['features']]

def jelaskan(row):
 """SHAP dihitung saat detail dibuka, memakai versi model prediksi tersebut."""
 fitur=json.loads(row['features'])
 try:
  path=Path(current_app.config['ARTIFACT_DIR'])/row['model_version']
  model,names=_artefak(str(path))
  _,drivers,protectors=explain(model,names,{k:fitur[k] for k in names},path/'shap_background.csv')
  return fitur,drivers,protectors
 except (OSError,LookupError,KeyError,ValueError):
  return fitur,json.loads(row['drivers'] or '[]'),json.loads(row['protectors'] or '[]')

def faktor_terjemahan(drivers,protectors,fitur):
 from .dictionary import kalimat,label,jenis_faktor
 def rows(items,arah):
  out=[]
  for d in items:
   nama=d['feature']
   out.append({'feature':nama,'label':label(nama),'sentence':kalimat(nama,fitur.get(nama),arah,fitur),
               'factor_type':jenis_faktor(nama),'contribution':round(float(d.get('shap',0)),4)})
  return out
 naik=rows(drivers,'naik');turun=rows(protectors,'turun')
 for r in naik+turun:r['actionable']=r['factor_type']=='dapat_ditindaklanjuti'
 return naik,turun

def kasus(sid):
 with db() as c:r=c.execute('SELECT * FROM cases WHERE student_id=?',(sid,)).fetchone()
 return dict(r) if r else None

def simpan_kasus(sid,status,tindakan,catatan,actor,reopen_note=None):
 lama=kasus(sid);status=status or (lama['status'] if lama else 'belum')
 if status not in STATUS_PENANGANAN:return None,'Status penanganan tidak dikenal'
 cid=lama['case_id'] if lama else str(uuid.uuid4())
 with db() as c:
  c.execute('INSERT INTO cases(case_id,student_id,status,tindakan,catatan,updated_by,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET status=?,tindakan=?,catatan=?,updated_by=?,updated_at=?',
            (cid,sid,status,tindakan,catatan,actor,now(),status,tindakan,catatan,actor,now()))
  if lama is None or lama['status']!=status:
   c.execute('INSERT INTO case_events(event_id,case_id,status_lama,status_baru,catatan,timestamp) VALUES(?,?,?,?,?,?)',
             (str(uuid.uuid4()),cid,lama['status'] if lama else None,status,reopen_note or catatan,now()))
 return cid,None

def buka_kembali(sid,snapshot):
 """Prediksi baru masih risiko tinggi → kasus yang dianggap tuntas dibuka lagi."""
 k=kasus(sid)
 if not k or k['status'] not in ('dipantau','selesai'):return
 simpan_kasus(sid,'belum',k['tindakan'],f"Dibuka kembali: prediksi terbaru tanggal {snapshot or now()[:10]}",k['updated_by'] or session.get('uid'),
              reopen_note=f"Dibuka kembali: prediksi terbaru tanggal {snapshot or now()[:10]}")

def _secret():
 """Kunci sesi stabil antar restart; tanpa ini semua pengguna ter-logout tiap deploy."""
 p=ROOT/'data/secret.key'
 if not p.exists():p.write_text(secrets.token_hex(32));p.chmod(0o600)
 return p.read_text().strip()

def create_app(config=None):
 app=Flask(__name__,static_folder=None)
 app.config.update(SECRET_KEY=os.environ.get('SPRAM_SECRET') or _secret(),DATABASE=str(ROOT/'data/spram.sqlite'),ARTIFACT_DIR=str(ROOT/'artifacts'),DATASET=str(ROOT.parent/'data.csv'),CREDENTIALS_FILE=str(ROOT/'data/demo-credentials.txt'),MAX_CONTENT_LENGTH=20*1024*1024)
 if config:app.config.update(config)
 init_db(app);Path(app.config['ARTIFACT_DIR']).mkdir(parents=True,exist_ok=True)
 if app.config.get('BOOTSTRAP_MODELS'):bootstrap_models(app)
 @app.before_request
 def csrf_guard():
  if request.method not in ('GET','HEAD','OPTIONS') and request.path.startswith('/api/'):
   if not session.get('csrf') or request.headers.get('X-CSRF-Token')!=session['csrf']:return jsonify(error='CSRF validation failed'),403
 @app.get('/api/health')
 def health():return jsonify(status='ok')
 @app.get('/api/auth/me')
 def me():
  session.setdefault('csrf',secrets.token_urlsafe(24));u=user();return jsonify(user=dict(u) if u else None,csrf_token=session['csrf'])
 @app.post('/api/auth/login')
 def login():
  b=request.get_json() or {}
  with db() as c:u=c.execute('SELECT * FROM users WHERE email=?',(b.get('email','').lower(),)).fetchone()
  if not u or u['status']!='active' or not check_password_hash(u['password_hash'],b.get('password','')):return jsonify(error='Email atau password salah'),401
  session.clear();session['uid']=u['id'];session['csrf']=secrets.token_urlsafe(24);audit('login','session',u['id']);return jsonify(user={k:u[k] for k in ('id','name','email','role')},csrf_token=session['csrf'])
 @app.post('/api/auth/logout')
 @auth
 def logout():audit('logout','session');session.clear();return jsonify(ok=True)
 @app.get('/api/model-schemas/<stage>/active')
 @auth
 def schema(stage):
  if stage not in ('intake','academic_update'):return jsonify(error='Invalid stage'),404
  try:
   from .dictionary import fitur as kamus_fitur,label
   data=model_data(stage)[3]
   for field in data['features']:
    name=field['name'];entry=kamus_fitur(name)
    field['label']=label(name);field['group']=entry.get('group');field['factor_type']=entry.get('factor_type')
    if entry.get('values'):
     field['categories']=[{'value':int(k) if k.lstrip('-').isdigit() else k,'label':v} for k,v in entry['values'].items()]
    if entry.get('help'):field['help']=entry['help']
   return jsonify(data)
  except LookupError as e:return jsonify(error=str(e)),409
 @app.get('/api/templates/<stage>.csv')
 @auth
 def template(stage):
  s=model_data(stage)[3];out=io.StringIO();csv.writer(out,delimiter=';').writerow(['student_id','snapshot_date','prediction_stage']+[x['name'] for x in s['features']]);return app.response_class(out.getvalue(),mimetype='text/csv')
 def predict_payload(b,save=True):
  sid=b.get('student_id');stage=b.get('stage') or b.get('prediction_stage');
  if stage not in ('intake','academic_update'):return None,(jsonify(error='Invalid stage'),422)
  if save and not allowed(sid):return None,(jsonify(error='Forbidden'),403)
  version,path,model,schema=model_data(stage);features=b.get('features') or {};errs={}
  for f in schema['features']:
   n=f['name'];v=features.get(n)
   try:v=float(v);errs[n]='Out of range' if v<f['min'] or v>f['max'] else None
   except (TypeError,ValueError):errs[n]='Required numeric value'
  errs={k:v for k,v in errs.items() if v}
  if errs:return None,(jsonify(error={'message':'Validation failed','fields':errs}),422)
  clean={f['name']:float(features[f['name']]) for f in schema['features']};import pandas as pd
  probs=model.predict_proba(pd.DataFrame([clean]))[0];label=CLASSES[int(probs.argmax())];base,drivers,protectors=explain(model,[f['name'] for f in schema['features']],clean,path/'shap_background.csv')
  result={'id':str(uuid.uuid4()),'student_id':sid,'stage':stage,'snapshot_date':b.get('snapshot_date'),'features':clean,'probabilities':dict(zip(CLASSES,map(float,probs))),'predicted_class':label,'class_label':label,'risk_band':risk_band(float(probs[0])),'model_version':version,'schema_version':schema['schema_version'],'top_drivers':drivers,'top_protectors':protectors,'created_at':now(),'disclaimer':'Kontribusi model bukan bukti sebab-akibat.'}
  if save:
   key=b.get('idempotency_key')
   with db() as c:
    old=c.execute('SELECT * FROM predictions WHERE idempotency_key=?',(key,)).fetchone() if key else None
    if old:return serialize_prediction(old),None
    c.execute('INSERT OR IGNORE INTO students(student_id,cohort,program_code) VALUES(?,?,?)',(sid,'—','—'))
    c.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(result['id'],sid,stage,result['snapshot_date'],json.dumps(clean),json.dumps(result['probabilities']),label,result['risk_band'],version,schema['schema_version'],json.dumps(drivers),json.dumps(protectors),key,result['created_at']))
   if result['risk_band']=='high':buka_kembali(sid,result['snapshot_date'])
  return result,None
 @app.post('/api/predictions')
 @auth
 def predictions():
  try:
   body=request.get_json() or {};sid=(body.get('student_id') or '').strip();stage=body.get('stage') or body.get('prediction_stage');key=body.get('idempotency_key')
   with db() as c:
    same=c.execute('SELECT * FROM predictions WHERE idempotency_key=?',(key,)).fetchone() if key else None
    existing=c.execute('SELECT id FROM predictions WHERE student_id=? AND stage=? AND snapshot_date IS ? LIMIT 1',(sid,stage,body.get('snapshot_date'))).fetchone()
   if same:return jsonify(serialize_prediction(same)),201
   if existing:return jsonify(error=f'Mahasiswa {sid} sudah memiliki prediksi Academic Update pada tanggal pencatatan itu. Gunakan tanggal snapshot berikutnya atau lihat hasil yang tersimpan.',duplicate=True),409
   result,error=predict_payload(body);return error or (jsonify(result),201)
  except LookupError as e:return jsonify(error=str(e)),409
 @app.get('/api/predictions/<pid>')
 @auth
 def prediction(pid):
  with db() as c:r=c.execute('SELECT * FROM predictions WHERE id=?',(pid,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  if not allowed(r['student_id']):return jsonify(error='Forbidden'),403
  return jsonify(serialize_prediction(r))
 @app.get('/api/students')
 @auth
 def students():
  from .dictionary import terjemahkan
  u=user();clauses=[];params=[]
  if u['role']!='admin':clauses.append('s.student_id IN (SELECT student_id FROM assignments WHERE advisor_id=?)');params.append(u['id'])
  q=request.args.get('q','').strip();stage=request.args.get('stage','').strip();risk=request.args.get('risk_band','').strip();prediction_class=request.args.get('prediction_class','').strip();handling=request.args.get('handling','').strip()
  if q:clauses.append('(s.student_id LIKE ? OR s.program_code LIKE ?)');params.extend([f'%{q}%']*2)
  if stage:clauses.append('p.stage=?');params.append(stage)
  if risk:clauses.append('p.risk_band=?');params.append(risk)
  if prediction_class:clauses.append('p.predicted_class=?');params.append(prediction_class)
  if handling=='belum':clauses.append("COALESCE(k.status,'belum')='belum'")
  elif handling:clauses.append("k.status=?");params.append(handling)
  where='WHERE '+' AND '.join(clauses) if clauses else ''
  with db() as c:rows=c.execute(f'''SELECT s.student_id,s.program_code,p.stage,p.predicted_class,p.risk_band,p.probabilities,p.features,
    k.status AS case_status,k.updated_at AS case_updated_at,
    (SELECT u2.name FROM assignments a2 JOIN users u2 ON u2.id=a2.advisor_id WHERE a2.student_id=s.student_id LIMIT 1) AS advisor_name
    FROM students s
    LEFT JOIN predictions p ON p.id=(SELECT id FROM predictions WHERE student_id=s.student_id ORDER BY created_at DESC LIMIT 1)
    LEFT JOIN cases k ON k.student_id=s.student_id {where} ORDER BY s.student_id''',params).fetchall()
  items=[]
  for r in rows:
   d=dict(r);features=json.loads(d.pop('features') or '{}')
   d['latest_prediction']={'stage':d.pop('stage'),'predicted_class':d.pop('predicted_class'),'risk_band':d.pop('risk_band'),'probabilities':json.loads(d.pop('probabilities')) if d['probabilities'] else None}
   d['info']={'program':terjemahkan('Course',features.get('Course')) if 'Course' in features else (d.get('program_code') or '—'),
              'age':terjemahkan('Age at enrollment',features.get('Age at enrollment')) if 'Age at enrollment' in features else '—',
              'gender':terjemahkan('Gender',features.get('Gender')) if 'Gender' in features else '—'}
   d['handling']={'status':d.pop('case_status') or 'belum','updated_at':d.pop('case_updated_at',None)}
   d['handling']['label']=STATUS_PENANGANAN.get(d['handling']['status'],d['handling']['status'])
   items.append(d)
  return jsonify(items=items,total=len(items))
 @app.get('/api/students/<sid>/timeline')
 @auth
 def timeline(sid):
  if not allowed(sid):return jsonify(error='Forbidden'),403
  with db() as c:s=c.execute('SELECT * FROM students WHERE student_id=?',(sid,)).fetchone();ps=c.execute('SELECT * FROM predictions WHERE student_id=? ORDER BY created_at DESC',(sid,)).fetchall();ins=c.execute('SELECT * FROM interventions WHERE student_id=? ORDER BY created_at DESC',(sid,)).fetchall()
  return jsonify(student=dict(s) if s else None,predictions=[serialize_prediction(x) for x in ps],interventions=[dict(x) for x in ins])
 @app.patch('/api/students/<sid>')
 @admin
 def student_update(sid):
  """Admin mengelola data induk mahasiswa. Bukan penanganan kasus."""
  b=request.get_json() or {}
  with db() as c:
   if not c.execute('SELECT 1 FROM students WHERE student_id=?',(sid,)).fetchone():return jsonify(error=f'Mahasiswa {sid} belum terdaftar di sistem'),404
   ubah={}
   for key in ('cohort','program_code','active_status'):
    if key in b:
     nilai=str(b[key] or '').strip()
     if not nilai:return jsonify(error=f'{key} tidak boleh kosong'),422
     if len(nilai)>32:return jsonify(error=f'{key} maksimal 32 karakter'),422
     if any(ord(ch)<32 for ch in nilai):return jsonify(error=f'{key} berisi karakter tidak sah'),422
     ubah[key]=nilai
   if not ubah:return jsonify(error='Tidak ada field yang diubah'),422
   c.execute('UPDATE students SET '+','.join(f'{k}=?' for k in ubah)+' WHERE student_id=?',[*ubah.values(),sid])
  audit('student_update','student',sid);return jsonify(student_id=sid,**ubah),200
 @app.get('/api/dictionary')
 @auth
 def dictionary_all():
  from .dictionary import kamus
  return jsonify(kamus())
 @app.get('/api/students/<sid>/detail')
 @auth
 def student_detail(sid):
  if not allowed(sid):return jsonify(error='Forbidden'),403
  from .dictionary import label_kelas,profil
  from .expert import PAGAR_AMAN,aturan_aktif,kontribusi,thresholds as ambang_aturan
  with db() as c:s=c.execute('SELECT * FROM students WHERE student_id=?',(sid,)).fetchone()
  induk=dict(s) if s else {'student_id':sid}
  row=prediksi_terakhir(sid);audit('student_detail','student',sid)
  if not row:
   return jsonify(student=induk,prediction=None,factors={'increase':[],'decrease':[],'background':[]},
                  profile=[],history=[],case=kasus(sid),statuses=STATUS_PENANGANAN,events=[])
  fitur,drivers,protectors=jelaskan(row)
  naik,turun=faktor_terjemahan(drivers,protectors,fitur)
  latar=[x for x in naik+turun if not x['actionable']]
  naik=[x for x in naik if x['actionable']];turun=[x for x in turun if x['actionable']]
  prob=json.loads(row['probabilities']);rules=aturan_db(aktif_saja=True)
  aktif=aturan_aktif(fitur,drivers,row['risk_band'],rules,ambang_aturan())
  for r in aktif:r['kontribusi']=kontribusi(r,drivers)
  aktif.sort(key=lambda r:(r.get('prioritas',99),-r['kontribusi']))
  with db() as c:
   history=[dict(x) for x in c.execute('SELECT * FROM predictions WHERE student_id=? ORDER BY created_at DESC',(sid,)).fetchall()]
  k=kasus(sid);events=[]
  if k:
   with db() as c:events=[dict(x) for x in c.execute('SELECT * FROM case_events WHERE case_id=? ORDER BY timestamp',(k['case_id'],)).fetchall()]
  tandai={x['feature'] for x in naik+turun+latar}
  return jsonify(student=induk,
                 prediction={'id':row['id'],'stage':row['stage'],'snapshot_date':row['snapshot_date'],
                             'predicted_class':row['predicted_class'],'class_label':label_kelas(row['predicted_class']),
                             'risk_band':row['risk_band'],'probabilities':prob,'model_version':row['model_version'],
                             'created_at':row['created_at'],'class_labels':{k2:label_kelas(k2) for k2 in prob}},
                 factors={'increase':naik[:6],'decrease':turun[:6],'background':latar[:6]},
                 profile=profil(fitur,tandai),
                 history=[{'id':x['id'],'stage':x['stage'],'snapshot_date':x['snapshot_date'],'created_at':x['created_at'],
                           'predicted_class':x['predicted_class'],'class_label':label_kelas(x['predicted_class']),
                           'risk_band':x['risk_band'],'probabilities':json.loads(x['probabilities'])} for x in history],
                 case={**k,'status_label':STATUS_PENANGANAN.get(k['status'],k['status'])} if k else None,
                 events=events,statuses=STATUS_PENANGANAN,
                 consultation={'active_rules':[{'rule_id':r['rule_id'],'nama':r['nama'],'hipotesis':r['hipotesis'],
                                                 'pertanyaan':r['pertanyaan'],'alasan':r['alasan'],'prioritas':r.get('prioritas',99)} for r in aktif],
                               'pagar_aman':PAGAR_AMAN},
                 thresholds=ambang_aturan())
 @app.post('/api/cases')
 @advisor_only
 def case_save():
  b=request.get_json() or {};sid=(b.get('student_id') or '').strip()
  if not allowed(sid):return jsonify(error='Forbidden'),403
  cid,err=simpan_kasus(sid,b.get('status'),b.get('tindakan'),b.get('catatan'),user()['id'])
  if err:return jsonify(error=err),422
  audit('case_update','student',sid);k=kasus(sid)
  return jsonify({**k,'status_label':STATUS_PENANGANAN.get(k['status'],k['status'])}),201
 @app.post('/api/consultations/preview')
 @auth
 def consultation_preview():
  from .expert import aturan_aktif,kontribusi,rekomendasi,thresholds as ambang_aturan
  b=request.get_json() or {};sid=(b.get('student_id') or '').strip()
  if not allowed(sid):return jsonify(error='Forbidden'),403
  row=prediksi_terakhir(sid)
  if not row:return jsonify(error='Mahasiswa belum memiliki prediksi'),409
  fitur,drivers,protectors=jelaskan(row)
  aktif=aturan_aktif(fitur,drivers,row['risk_band'],aturan_db(aktif_saja=True),ambang_aturan())
  for r in aktif:r['kontribusi']=kontribusi(r,drivers)
  aktif.sort(key=lambda r:(r.get('prioritas',99),-r['kontribusi']))
  hasil=rekomendasi(aktif,b.get('jawaban') or {},row['risk_band'],drivers)
  return jsonify({'prediction_id':row['id'],'risk_band':row['risk_band'],
                  'aturan_aktif':[{'rule_id':r['rule_id'],'nama':r['nama'],'hipotesis':r['hipotesis'],'pertanyaan':r['pertanyaan'],
                                   'alasan':r['alasan'],'prioritas':r.get('prioritas',99),'kontribusi':r['kontribusi']} for r in aktif],**hasil})
 @app.post('/api/consultations')
 @advisor_only
 def consultation_save():
  from .expert import aturan_aktif,kontribusi,thresholds as ambang_aturan
  b=request.get_json() or {};sid=(b.get('student_id') or '').strip()
  if not allowed(sid):return jsonify(error='Forbidden'),403
  row=prediksi_terakhir(sid)
  if not row:return jsonify(error='Mahasiswa belum memiliki prediksi'),409
  fitur,drivers,_=jelaskan(row)
  aktif=aturan_aktif(fitur,drivers,row['risk_band'],aturan_db(aktif_saja=True),ambang_aturan())
  cid=str(uuid.uuid4())
  with db() as c:c.execute('INSERT INTO consultations VALUES(?,?,?,?,?,?,?)',(cid,sid,row['id'],user()['id'],json.dumps(b.get('jawaban') or {}),json.dumps([r['rule_id'] for r in aktif]),now()))
  audit('consultation_save','student',sid)
  return jsonify(consult_id=cid,student_id=sid,aturan_aktif=[r['rule_id'] for r in aktif]),201
 @app.get('/api/students/<sid>/consultations')
 @auth
 def consultation_list(sid):
  if not allowed(sid):return jsonify(error='Forbidden'),403
  with db() as c:rows=[dict(x) for x in c.execute('SELECT * FROM consultations WHERE student_id=? ORDER BY created_at DESC',(sid,)).fetchall()]
  for r in rows:r['jawaban']=json.loads(r['jawaban_json']);r['aturan_aktif']=json.loads(r['aturan_aktif_json'])
  return jsonify(items=rows)
 @app.get('/api/rules')
 @admin
 def rules_list():
  items=aturan_db()
  from .expert import thresholds as ambang_aturan
  return jsonify(items=items,thresholds=ambang_aturan(),chat_scope=chat_scope_db())
 @app.put('/api/rules/chat-scope')
 @admin
 def chat_scope_update():
  from .advisor_chat import DEFAULT_SCOPE
  b=request.get_json() or {}
  scope={k:(b.get(k) if isinstance(b.get(k),str) else DEFAULT_SCOPE[k])
         for k in ('lingkup','ditolak','nada','catatan')}
  scope['aktif']=bool(b.get('aktif',True))
  for k,v in scope.items():
   if isinstance(v,str) and len(v)>1200:return jsonify(error=f'{k} maksimal 1200 karakter'),422
  with db() as c:c.execute("INSERT OR REPLACE INTO settings VALUES('chat_scope',?)",(json.dumps(scope),))
  audit('chat_scope_update','rule','chat_scope');return jsonify(**scope),200
 @app.post('/api/rules')
 @admin
 def rule_create():
  from .expert import validasi_rule
  b=request.get_json() or {};rule={'rule_id':(b.get('rule_id') or '').strip().upper(),'nama':b.get('nama'),'kondisi':b.get('kondisi') or [],
       'kondisi_atau':b.get('kondisi_atau') or [],'hipotesis':b.get('hipotesis'),'pertanyaan':b.get('pertanyaan'),
       'tindakan':b.get('tindakan') or {},'prioritas':b.get('prioritas',99),'topik':b.get('topik','umum')}
  if not rule['rule_id'] or not rule['nama']:return jsonify(error='ID dan nama aturan wajib diisi'),422
  errs=validasi_rule(rule,fitur_names())
  if errs:return jsonify(error='; '.join(errs),errors=errs),422
  with db() as c:
   if c.execute('SELECT 1 FROM rules WHERE rule_id=?',(rule['rule_id'],)).fetchone():return jsonify(error='ID aturan sudah dipakai'),409
   c.execute('INSERT INTO rules(rule_id,nama,kondisi_json,hipotesis,pertanyaan,tindakan_json,prioritas,aktif,topik,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
             (rule['rule_id'],rule['nama'],json.dumps({'dan':rule['kondisi'],'atau':rule['kondisi_atau'],'fallback':bool(b.get('fallback'))}),
              rule['hipotesis'],rule['pertanyaan'],json.dumps(rule['tindakan']),rule['prioritas'],1,rule['topik'],user()['id'],now()))
  audit('rule_create','rule',rule['rule_id']);return jsonify(rule_id=rule['rule_id']),201
 @app.patch('/api/rules/<rid>')
 @admin
 def rule_update(rid):
  from .expert import validasi_rule
  b=request.get_json() or {}
  with db() as c:row=c.execute('SELECT * FROM rules WHERE rule_id=?',(rid,)).fetchone()
  if not row:return jsonify(error='Aturan tidak ditemukan'),404
  lama=dict(row);kondisi=json.loads(lama['kondisi_json'] or '{}')
  rule={'rule_id':rid,'nama':b.get('nama',lama['nama']),'kondisi':b.get('kondisi',kondisi.get('dan',[])),
        'kondisi_atau':b.get('kondisi_atau',kondisi.get('atau',[])),'hipotesis':b.get('hipotesis',lama['hipotesis']),
        'pertanyaan':b.get('pertanyaan',lama['pertanyaan']),'tindakan':b.get('tindakan',json.loads(lama['tindakan_json'] or '{}')),
        'prioritas':b.get('prioritas',lama['prioritas']),'topik':b.get('topik',lama['topik'])}
  errs=validasi_rule(rule,fitur_names())
  if errs:return jsonify(error='; '.join(errs),errors=errs),422
  aktif=int(b.get('aktif',lama['aktif']))
  with db() as c:c.execute('UPDATE rules SET nama=?,kondisi_json=?,hipotesis=?,pertanyaan=?,tindakan_json=?,prioritas=?,aktif=?,topik=?,updated_by=?,updated_at=? WHERE rule_id=?',
      (rule['nama'],json.dumps({'dan':rule['kondisi'],'atau':rule['kondisi_atau'],'fallback':bool(b.get('fallback',kondisi.get('fallback',False)))}),
       rule['hipotesis'],rule['pertanyaan'],json.dumps(rule['tindakan']),rule['prioritas'],aktif,rule['topik'],user()['id'],now(),rid))
  audit('rule_update','rule',rid);return jsonify(rule_id=rid,aktif=aktif)
 @app.delete('/api/rules/<rid>')
 @admin
 def rule_delete(rid):
  with db() as c:
   if not c.execute('SELECT 1 FROM rules WHERE rule_id=?',(rid,)).fetchone():return jsonify(error='Aturan tidak ditemukan'),404
   c.execute('UPDATE rules SET aktif=0,updated_by=?,updated_at=? WHERE rule_id=?',(user()['id'],now(),rid))
  audit('rule_disable','rule',rid);return jsonify(rule_id=rid,aktif=0)
 @app.get('/api/dashboard/summary')
 @auth
 def dashboard():
  u=user();scope='' if u['role']=='admin' else ' WHERE student_id IN (SELECT student_id FROM assignments WHERE advisor_id=?)';p=[] if u['role']=='admin' else [u['id']]
  with db() as c:
   total=c.execute('SELECT count(*) FROM students'+scope,p).fetchone()[0]
   rows=c.execute('SELECT * FROM predictions'+scope+' ORDER BY created_at DESC',p).fetchall()
   cases={x['student_id']:x for x in c.execute('SELECT * FROM cases').fetchall()}
   iv=c.execute("SELECT count(*) FROM interventions WHERE status!='completed'"+('' if u['role']=='admin' else ' AND student_id IN (SELECT student_id FROM assignments WHERE advisor_id=?)'),p).fetchone()[0]
  latest={};[latest.setdefault(r['student_id'],r) for r in rows]
  risks={x:sum(r['risk_band']==x for r in latest.values()) for x in ('low','medium','high')}
  def item(r):
   d=serialize_prediction(r);k=cases.get(r['student_id'])
   d['case']={'status':k['status'],'status_label':STATUS_PENANGANAN.get(k['status'],k['status']),'updated_at':k['updated_at']} if k else {'status':'belum','status_label':STATUS_PENANGANAN['belum'],'updated_at':None}
   return d
  tinggi=[item(r) for r in latest.values() if r['risk_band']=='high']
  tinggi.sort(key=lambda x:-x['probabilities'].get('Dropout',0))
  belum=[x for x in tinggi if x['case']['status']=='belum']
  ditangani=[x for x in tinggi if x['case']['status']!='belum']
  return jsonify(total_students=total,total_predictions=len(rows),risk_distribution=risks,
                 priority_students=belum,high_risk_untreated=belum,high_risk_monitored=ditangani,
                 pending_interventions=iv,untreated_count=len(belum),monitored_count=len(ditangani),
                 class_distribution={x:sum(r['predicted_class']==x for r in latest.values()) for x in CLASSES},trend=[])
 @app.post('/api/interventions')
 @advisor_only
 def intervention():
  b=request.get_json() or {};sid=b.get('student_id')
  if not allowed(sid):return jsonify(error='Forbidden'),403
  iid=str(uuid.uuid4());
  with db() as c:c.execute('INSERT INTO interventions VALUES(?,?,?,?,?,?,?,?)',(iid,sid,b.get('prediction_id'),b.get('type'),b.get('note'),b.get('due_date'),b.get('status','planned'),now()))
  return jsonify(id=iid,status=b.get('status','planned')),201
 @app.patch('/api/interventions/<iid>')
 @advisor_only
 def intervention_patch(iid):
  b=request.get_json() or {}
  with db() as c:r=c.execute('SELECT * FROM interventions WHERE id=?',(iid,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  if not allowed(r['student_id']):return jsonify(error='Forbidden'),403
  with db() as c:c.execute('UPDATE interventions SET status=? WHERE id=?',(b.get('status'),iid));r=c.execute('SELECT * FROM interventions WHERE id=?',(iid,)).fetchone()
  return jsonify(dict(r))
 @app.post('/api/assistant')
 @advisor_only
 def assistant():
  b=request.get_json() or {};pid=b.get('prediction_id');intent=b.get('intent') or tebak_intent(b.get('question'))
  with db() as c:
   r=c.execute('SELECT * FROM predictions WHERE id=?',(pid,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  if not allowed(r['student_id']):return jsonify(error='Forbidden'),403
  return jsonify(answer=jawab_asisten(r,intent),intent=intent,prediction_id=pid,
                 disclaimer='Penjelasan bukan bukti sebab-akibat dan bukan keputusan otomatis.')
 @app.get('/api/students/<sid>/recommendations')
 @advisor_only
 def student_recommendations(sid):
  """Saran bersyarat; jawaban dosen tidak mengubah prediksi."""
  if not allowed(sid):return jsonify(error='Forbidden'),403
  row=prediksi_terakhir(sid)
  if not row:return jsonify(error='Mahasiswa belum memiliki prediksi'),409
  from .advisor_chat import build_context
  from .expert import aturan_aktif,thresholds
  features=json.loads(row['features']);drivers=json.loads(row['drivers'] or '[]')
  active=aturan_aktif(features,drivers,row['risk_band'],aturan_db(True),thresholds())
  safe=build_context(row,active)
  # Kompatibilitas UI: tindakan sementara saja, bukan tindakan bersyarat yang belum terverifikasi.
  recommendations=[{'rule_id':r['rule_id'],'nama':r['nama'],'hipotesis':r['hipotesis'],
                    'pertanyaan':r['pertanyaan'],'alasan':r.get('alasan',[]),
                    'verifikasi':r['pertanyaan'],'sementara':r['tindakan'].get('belum_tahu',[]),
                    'jika_ya':r['tindakan'].get('ya',[]),'jika_tidak':r['tindakan'].get('tidak',[]),
                    'tindakan':r['tindakan'].get('belum_tahu',[])} for r in active[:6]]
  return jsonify(prediction_id=row['id'],risk_band=row['risk_band'],
                 rekomendasi=recommendations,pagar_aman=safe['batasan'])
 @app.post('/api/students/<sid>/assistant')
 @advisor_only
 def student_assistant(sid):
  if not allowed(sid):return jsonify(error='Forbidden'),403
  b=request.get_json(silent=True) or {}
  question=b.get('question') or next((label for key,label in (
   ('why','Mengapa risiko ini?'),('intervention','Apa langkah yang perlu diverifikasi?'),
   ('changes','Apa yang berubah?'),('confidence','Seberapa yakin prediksi?'),
   ('profile','Data apa yang dipakai?')) if b.get('intent')==key),'')
  if not isinstance(question,str) or not question.strip() or len(question)>2000:
   return jsonify(error='Pertanyaan wajib diisi, maksimal 2000 karakter'),422
  history=b.get('history',[])
  if not isinstance(history,list):return jsonify(error='Riwayat percakapan harus berupa daftar'),422
  row=prediksi_terakhir(sid)
  if not row:return jsonify(error='Mahasiswa belum memiliki prediksi'),409
  from .advisor_chat import answer,build_context,call_model
  from .chat_cache import kunci as kunci_cache
  from .expert import aturan_aktif,thresholds
  features=json.loads(row['features']);drivers=json.loads(row['drivers'] or '[]')
  active=aturan_aktif(features,drivers,row['risk_band'],aturan_db(True),thresholds())
  ctx=build_context(row,active)
  batas=chat_scope_db()
  # Sesi percakapan: milik dosen ini saja, disimpan agar riwayat tetap ada.
  sesi=b.get('session_id');info=None
  with db() as c:
   if sesi:
    s=c.execute('SELECT * FROM chat_sessions WHERE id=?',(sesi,)).fetchone()
    if not s or s['advisor_id']!=user()['id'] or s['student_id']!=sid:
     return jsonify(error='Percakapan tidak ditemukan'),404
    hist=[dict(r) for r in c.execute('SELECT role,content FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT 8',(sesi,)).fetchall()]
    if hist:history=[{'role':h['role'],'content':h['content']} for h in reversed(hist)]
  ck=kunci_cache(question,ctx,scope=batas)
  with db() as c:hit=c.execute('SELECT answer,mode FROM chat_cache WHERE cache_key=?',(ck,)).fetchone()
  if hit:
   # Pertanyaan serupa: jangan panggil model lagi (hemat token, jawaban konsisten).
   result={'mode':hit['mode'],'answer':hit['answer'],'cached':True}
   with db() as c:c.execute('UPDATE chat_cache SET hits=hits+1,last_hit=? WHERE cache_key=?',(now(),ck))
  else:
   result=answer(question,history,ctx,llm=call_model,scope=batas)
   result['cached']=False
   if result.get('mode')=='ai':
    with db() as c:c.execute('INSERT OR REPLACE INTO chat_cache(cache_key,answer,mode,hits,created_at,last_hit) VALUES(?,?,?,0,?,?)',
                             (ck,result['answer'],result['mode'],now(),now()))
  if sesi:
   judul=(question.strip()[:60]+'…') if len(question.strip())>60 else question.strip()
   with db() as c:
    c.execute('INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)',(sesi,'user',question,now()))
    c.execute('INSERT INTO chat_messages(session_id,role,content,created_at) VALUES(?,?,?,?)',(sesi,'assistant',result['answer'],now()))
    c.execute('UPDATE chat_sessions SET updated_at=?,title=CASE WHEN title=? THEN ? ELSE title END WHERE id=?',
              (now(),'Percakapan baru',judul,sesi))
    info=dict(c.execute('SELECT id,student_id,title FROM chat_sessions WHERE id=?',(sesi,)).fetchone())
  return jsonify(student_id=sid,prediction_id=row['id'],intent=b.get('intent') or tebak_intent(question),
                 **result,session=info,disclaimer='Perkiraan model bukan diagnosis; dosen memverifikasi sebelum bertindak.')
 @app.post('/api/batch-jobs')
 @auth
 def batch_create():
  stage=request.form.get('stage');f=request.files.get('file')
  if not f:return jsonify(error='File CSV atau Excel wajib diunggah'),422
  if stage not in ('intake','academic_update'):return jsonify(error='Invalid stage'),422
  blob=f.read();suffix=Path(f.filename or '').suffix.lower()
  if suffix not in ('.csv','.xlsx'):return jsonify(error='Format file tidak didukung. Upload file CSV atau Excel dengan ekstensi .csv atau .xlsx.'),422
  if suffix=='.xlsx':
   try:
    import zipfile,xml.etree.ElementTree as ET
    ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(io.BytesIO(blob)) as book:
     shared=[''.join(x.itertext()) for x in ET.fromstring(book.read('xl/sharedStrings.xml')).findall(ns+'si')] if 'xl/sharedStrings.xml' in book.namelist() else []
     sheet=ET.fromstring(book.read('xl/worksheets/sheet1.xml'));rows=[]
     for node in sheet.findall('.//'+ns+'row'):
      values=[]
      for cell in node.findall(ns+'c'):
       index=0
       for ch in ''.join(x for x in cell.get('r','A1') if x.isalpha()):index=index*26+ord(ch.upper())-64
       while len(values)<index:values.append('')
       value=cell.find(ns+'v');text='' if value is None else value.text or ''
       if cell.get('t')=='s':text=shared[int(text)]
       elif cell.get('t')=='inlineStr':text=''.join(cell.itertext())
       values[index-1]=text
      rows.append(values)
    headers=[str(x).strip().strip('"').rstrip('\t') for x in rows[0]];reader=[dict(zip(headers,row)) for row in rows[1:]];header_line=';'.join(headers)
   except (KeyError,ValueError,zipfile.BadZipFile,ET.ParseError,IndexError):return jsonify(error='File Excel tidak valid'),422
  else:
   try:raw=blob.decode('utf-8-sig')
   except UnicodeDecodeError:return jsonify(error='CSV harus memakai encoding UTF-8'),422
   lines_raw=raw.split('\n');header_line=lines_raw[0] if lines_raw else ''
   header_clean=';'.join(h.strip().strip('"').strip().rstrip('\t') for h in header_line.split(';'))
   normalized=header_clean+'\n'+'\n'.join(lines_raw[1:])
   reader=csv.DictReader(io.StringIO(normalized),delimiter=';')
  schema=model_data(stage)[3];feature_names=[x['name'] for x in schema['features']]
  schema_features=schema['features']
  actual_headers=[h.strip().strip('"').rstrip('\t') for h in header_line.split(';')]
  required_headers=['student_id','snapshot_date']+feature_names
  missing_columns=[h for h in required_headers if h not in actual_headers]
  unknown_columns=[h for h in actual_headers if h and h not in required_headers and h not in ('prediction_stage','Target')]
  if missing_columns or unknown_columns:
   messages=[]
   if missing_columns:messages.append('Kolom wajib tidak tersedia: '+', '.join(missing_columns))
   if unknown_columns:messages.append('Nama kolom tidak dikenali: '+', '.join(unknown_columns))
   return jsonify(error='Struktur CSV bermasalah. '+'; '.join(messages)+'. Gunakan template CSV tanpa mengubah nama kolom.',missing_columns=missing_columns,unknown_columns=unknown_columns,can_predict=False),422
  has_sid='student_id' in [h.strip().strip('"').rstrip('\t') for h in header_line.split(';')]
  has_date='snapshot_date' in [h.strip().strip('"').rstrip('\t') for h in header_line.split(';')]
  today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
  valid=[];errors=[];skipped=[];seen=set()
  with db() as c:existing_pairs={(r['student_id'],r['snapshot_date']) for r in c.execute('SELECT student_id,snapshot_date FROM predictions WHERE stage=?',(stage,)).fetchall()}
  for line,row in enumerate(reader,2):
   if not any(v and v.strip() for v in row.values()): continue  # skip empty rows
   sid=row.get('student_id','').strip() if has_sid else f'BATCH-{line:05d}'
   if not sid: sid=f'BATCH-{line:05d}'
   snap=row.get('snapshot_date','').strip() if has_date else today
   if not snap: snap=today
   if (sid,snap) in existing_pairs:
    skipped.append({'row':line,'student_id':sid,'reason':'Sudah memiliki prediksi pada tanggal itu'});continue
   if sid in seen:
    skipped.append({'row':line,'student_id':sid,'reason':'Duplikat dalam file CSV'});continue
   seen.add(sid)
   features={};row_errors=[]
   for fn in feature_names:
    v=row.get(fn)
    if v is None or v.strip()=='':
     row_errors.append(fn)
    else:
     features[fn]=v.strip()
   if row_errors:
    errors.append({'row':line,'message':f'Missing fields: {", ".join(row_errors[:5])}'+(f' +{len(row_errors)-5} more' if len(row_errors)>5 else '')})
    continue
   payload={'student_id':sid,'snapshot_date':snap,'stage':stage,'features':features}
   # Light validation: type+range check only (no model inference/SHAP)
   field_errs=[]
   for feat in schema_features:
    fn2=feat['name'];v2=features.get(fn2)
    try:
     fv=float(v2)
     if fv<feat['min'] or fv>feat['max']:field_errs.append(fn2)
    except (TypeError,ValueError):field_errs.append(fn2)
   if field_errs:
    errors.append({'row':line,'message':f'Invalid values: {", ".join(field_errs[:5])}'+(f' +{len(field_errs)-5} more' if len(field_errs)>5 else '')})
   else:
    valid.append(payload)
  jid=str(uuid.uuid4());status='invalid' if errors else 'validated'
  with db() as c:c.execute('INSERT INTO batch_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(jid,user()['id'],stage,status,len(valid),len(errors),json.dumps(valid),json.dumps(errors),json.dumps([]),now()))
  return jsonify(id=jid,status=status,valid_count=len(valid),invalid_count=len(errors),skipped_count=len(skipped),skipped=skipped[:50],errors=errors[:50],preview=valid[:10],can_predict=not errors and bool(valid)),201
 def run_batch(jid):
  with app.app_context():
   with db() as c:j=c.execute('SELECT * FROM batch_jobs WHERE id=?',(jid,)).fetchone();c.execute("UPDATE batch_jobs SET status='running' WHERE id=?",(jid,))
   results=[]
   for row in json.loads(j['valid_rows']):
    with app.test_request_context():
     # Restore uploader identity: Flask sessions are request-local and do not
     # cross into worker threads. Scope is checked again before persistence.
     session['uid']=j['owner']
     result,error=predict_payload(row,True)
     if not error:result['status']='success';results.append(result)
   status='partial' if j['invalid_count'] else 'completed'
   with db() as c:c.execute('UPDATE batch_jobs SET status=?,results=? WHERE id=?',(status,json.dumps(results),jid))
 @app.post('/api/batch-jobs/<jid>/run')
 @auth
 def batch_run(jid):
  with db() as c:j=c.execute('SELECT owner,status,invalid_count FROM batch_jobs WHERE id=?',(jid,)).fetchone()
  if not j:return jsonify(error='Job tidak ditemukan'),404
  if j['owner']!=user()['id'] and user()['role']!='admin':return jsonify(error='Forbidden'),403
  if j['status']!='validated' or j['invalid_count']:return jsonify(error='CSV masih bermasalah. Perbaiki semua baris invalid, upload ulang, lalu jalankan prediksi.'),409
  threading.Thread(target=run_batch,args=(jid,),daemon=True).start();return jsonify(id=jid,status='queued'),202
 @app.get('/api/batch-jobs/<jid>')
 @auth
 def batch_get(jid):
  with db() as c:r=c.execute('SELECT * FROM batch_jobs WHERE id=?',(jid,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  if r['owner']!=user()['id'] and user()['role']!='admin':return jsonify(error='Forbidden'),403
  d=dict(r);d['errors']=json.loads(d['errors']);d['results']=json.loads(d['results']);d.pop('valid_rows');return jsonify(d)
 @app.get('/api/batch-jobs/<jid>/export')
 @auth
 def batch_export(jid):
  with db() as c:r=c.execute('SELECT owner,results FROM batch_jobs WHERE id=?',(jid,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  if r['owner']!=user()['id'] and user()['role']!='admin':return jsonify(error='Forbidden'),403
  out=io.StringIO();w=csv.writer(out);w.writerow(['student_id','prediction','status','probability_dropout','probability_enrolled','probability_graduate']);[w.writerow([formula(x['student_id']),x['predicted_class'],x.get('status','success'),x['probabilities'].get('Dropout',0),x['probabilities'].get('Enrolled',0),x['probabilities'].get('Graduate',0)]) for x in json.loads(r['results'])];return app.response_class(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="hasil-prediksi-{jid}.csv"'})
 @app.get('/api/admin/users')
 @admin
 def users():
  with db() as c:return jsonify(items=[dict(x) for x in c.execute('SELECT id,name,email,role,status FROM users')])
 @app.get('/api/admin/audit')
 @admin
 def audits():
  with db() as c:items=[dict(x) for x in c.execute('SELECT * FROM audits ORDER BY id DESC')]
  return jsonify(items=items,total=len(items))
 @app.get('/api/admin/audit/export')
 @admin
 def audit_export():
  out=io.StringIO();w=csv.writer(out);w.writerow(['waktu','aktor','aksi','resource','resource_id','hasil'])
  with db() as c:
   for r in c.execute('SELECT a.*,u.email FROM audits a LEFT JOIN users u ON u.id=a.actor ORDER BY a.id DESC'):
    w.writerow([r['created_at'],formula(r['email'] or r['actor'] or ''),formula(r['action']),formula(r['resource']),formula(r['resource_id'] or ''),r['outcome']])
  return app.response_class(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="audit-spram.csv"'})
 @app.post('/api/admin/users')
 @admin
 def user_create():
  b=request.get_json() or {};email=(b.get('email') or '').strip().lower();password=b.get('password') or ''
  if not email or len(password)<12:return jsonify(error='Email wajib dan password minimal 12 karakter'),422
  if b.get('role') not in ('admin','advisor'):return jsonify(error='Peran harus admin atau advisor'),422
  with db() as c:
   if c.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():return jsonify(error='Email sudah terdaftar'),409
   c.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',(b.get('name') or email,email,generate_password_hash(password),b['role']))
   uid=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()[0]
  audit('user_create','user',uid);return jsonify(id=uid,email=email,role=b['role']),201
 @app.patch('/api/admin/users/<int:uid>')
 @admin
 def user_update(uid):
  b=request.get_json() or {}
  with db() as c:
   if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():return jsonify(error='Pengguna tidak ditemukan'),404
   if b.get('status') in ('active','disabled'):c.execute('UPDATE users SET status=? WHERE id=?',(b['status'],uid))
   if b.get('name'):c.execute('UPDATE users SET name=? WHERE id=?',(b['name'],uid))
  audit('user_update','user',uid);return jsonify(id=uid,ok=True)
 @app.get('/api/admin/assignments')
 @admin
 def assignments_list():
  with db() as c:
   rows=c.execute('SELECT a.advisor_id,a.student_id,u.name AS advisor_name FROM assignments a LEFT JOIN users u ON u.id=a.advisor_id ORDER BY a.advisor_id,a.student_id').fetchall()
   counts={r['advisor_id']:r['n'] for r in c.execute('SELECT advisor_id,count(*) AS n FROM assignments GROUP BY advisor_id').fetchall()}
   advisors=[dict(r,n=counts.get(r['id'],0)) for r in c.execute("SELECT id,name,email FROM users WHERE role='advisor' ORDER BY name").fetchall()]
  return jsonify(items=[dict(x) for x in rows],advisors=advisors,max_bimbingan=MAX_BIMBINGAN)
 @app.post('/api/admin/assignments')
 @admin
 def assignments_create():
  b=request.get_json() or {};advisor=b.get('advisor_id')
  sids=b.get('student_ids') or ([b['student_id']] if b.get('student_id') else [])
  sids=[str(x).strip() for x in sids if str(x).strip()]
  if not advisor or not sids:return jsonify(error='Dosen wali dan minimal satu mahasiswa wajib dipilih'),422
  with db() as c:
   u=c.execute("SELECT id,name FROM users WHERE id=? AND role='advisor'",(advisor,)).fetchone()
   if not u:return jsonify(error='Dosen wali tidak ditemukan'),404
   ada={x['student_id'] for x in c.execute('SELECT student_id FROM students').fetchall()}
   asing=[s for s in sids if s not in ada]
   if asing:return jsonify(error='Mahasiswa belum terdaftar di sistem: '+', '.join(asing[:10])),422
   sudah=c.execute('SELECT a.student_id,u.name AS advisor_name FROM assignments a LEFT JOIN users u ON u.id=a.advisor_id WHERE a.student_id IN (%s)'%','.join('?'*len(sids)),sids).fetchall()
   if sudah:
    rincian='; '.join(f"{x['student_id']} sudah dibimbing {x['advisor_name'] or 'dosen lain'}" for x in sudah[:10])
    return jsonify(error=f'Mahasiswa berikut sudah punya dosen wali dan tidak dapat ditetapkan lagi: {rincian}. Lepas atau ganti dosen walinya terlebih dahulu.',
                   already_assigned=[x['student_id'] for x in sudah]),409
   dipunya=c.execute('SELECT count(*) FROM assignments WHERE advisor_id=?',(advisor,)).fetchone()[0]
   if dipunya+len(sids)>MAX_BIMBINGAN:
    return jsonify(error=f'{u["name"]} sudah membimbing {dipunya} mahasiswa. Batas maksimal {MAX_BIMBINGAN} per dosen wali, sisa slot {max(MAX_BIMBINGAN-dipunya,0)}.',
                   quota_exceeded=True,current=dipunya,max=MAX_BIMBINGAN,requested=len(sids)),422
   try:c.executemany('INSERT INTO assignments(advisor_id,student_id) VALUES(?,?)',[(advisor,s) for s in sids])
   except sqlite3.IntegrityError:return jsonify(error='Sebagian mahasiswa sudah punya dosen wali'),409
  audit('assignment_create','advisor',advisor);return jsonify(advisor_id=advisor,student_ids=sids,count=len(sids)),201
 @app.patch('/api/admin/assignments')
 @admin
 def assignments_move():
  """Ganti dosen wali seorang mahasiswa (pindah, bukan menambah baris)."""
  b=request.get_json() or {};advisor=b.get('advisor_id');sid=str(b.get('student_id') or '').strip()
  if not advisor or not sid:return jsonify(error='Dosen wali dan mahasiswa wajib dipilih'),422
  with db() as c:
   u=c.execute("SELECT id,name FROM users WHERE id=? AND role='advisor'",(advisor,)).fetchone()
   if not u:return jsonify(error='Dosen wali tidak ditemukan'),404
   if not c.execute('SELECT 1 FROM students WHERE student_id=?',(sid,)).fetchone():return jsonify(error=f'Mahasiswa {sid} belum terdaftar di sistem'),422
   lama=c.execute('SELECT advisor_id FROM assignments WHERE student_id=?',(sid,)).fetchone()
   if lama and lama['advisor_id']==int(advisor):return jsonify(error=f'{sid} sudah dibimbing {u["name"]}'),409
   dipunya=c.execute('SELECT count(*) FROM assignments WHERE advisor_id=?',(advisor,)).fetchone()[0]
   if dipunya>=MAX_BIMBINGAN:
    return jsonify(error=f'{u["name"]} sudah membimbing {dipunya} mahasiswa (batas maksimal {MAX_BIMBINGAN}).',
                   quota_exceeded=True,current=dipunya,max=MAX_BIMBINGAN),422
   c.execute('INSERT INTO assignments(advisor_id,student_id) VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET advisor_id=excluded.advisor_id',(advisor,sid))
  audit('assignment_move','advisor',advisor);return jsonify(student_id=sid,advisor_id=advisor,moved=bool(lama)),200
 @app.delete('/api/admin/assignments')
 @admin
 def assignments_delete():
  advisor=request.args.get('advisor_id');sid=request.args.get('student_id')
  if not sid:return jsonify(error='student_id wajib'),422
  with db() as c:
   if advisor:
    cur=c.execute('DELETE FROM assignments WHERE advisor_id=? AND student_id=?',(advisor,sid))
   else:
    cur=c.execute('DELETE FROM assignments WHERE student_id=?',(sid,))
   if not cur.rowcount:return jsonify(error=f'{sid} belum punya dosen wali'),404
  audit('assignment_delete','advisor',advisor or '');return jsonify(ok=True,student_id=sid),200
 @app.get('/api/chat/sessions')
 @advisor_only
 def chat_sessions_list():
  with db() as c:rows=c.execute('SELECT id,student_id,title,created_at,updated_at FROM chat_sessions WHERE advisor_id=? ORDER BY updated_at DESC',
                                (user()['id'],)).fetchall()
  return jsonify(items=[dict(r) for r in rows])
 @app.post('/api/chat/sessions')
 @advisor_only
 def chat_session_create():
  b=request.get_json(silent=True) or {};sid=(b.get('student_id') or '').strip()
  if not sid:return jsonify(error='Mahasiswa wajib dipilih'),422
  if not allowed(sid):return jsonify(error='Forbidden'),403
  new=str(uuid.uuid4())
  with db() as c:c.execute('INSERT INTO chat_sessions(id,advisor_id,student_id,title,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                           (new,user()['id'],sid,'Percakapan baru',now(),now()))
  return jsonify(id=new,student_id=sid,title='Percakapan baru'),201
 @app.get('/api/chat/sessions/<sid>/messages')
 @advisor_only
 def chat_messages_list(sid):
  with db() as c:
   s=c.execute('SELECT * FROM chat_sessions WHERE id=?',(sid,)).fetchone()
   if not s or s['advisor_id']!=user()['id']:return jsonify(error='Percakapan tidak ditemukan'),404
   rows=c.execute('SELECT role,content,created_at FROM chat_messages WHERE session_id=? ORDER BY id',(sid,)).fetchall()
  return jsonify(id=sid,title=s['title'],student_id=s['student_id'],items=[dict(r) for r in rows])
 @app.delete('/api/chat/sessions/<sid>')
 @advisor_only
 def chat_session_delete(sid):
  with db() as c:
   s=c.execute('SELECT advisor_id FROM chat_sessions WHERE id=?',(sid,)).fetchone()
   if not s or s['advisor_id']!=user()['id']:return jsonify(error='Percakapan tidak ditemukan'),404
   c.execute('DELETE FROM chat_messages WHERE session_id=?',(sid,));c.execute('DELETE FROM chat_sessions WHERE id=?',(sid,))
  audit('chat_session_delete','chat',sid);return jsonify(ok=True),200
 @app.get('/api/admin/llm/providers')
 @admin
 def llm_providers_list():
  from .llm_providers import samarkan
  with db() as c:
   rows=[dict(r) for r in c.execute('SELECT id,name,base_url,api_key_enc,models_json,updated_at FROM llm_providers ORDER BY name').fetchall()]
   cfg=c.execute('SELECT provider_id,model,updated_at FROM llm_config WHERE id=1').fetchone()
  aktif=dict(cfg) if cfg else {'provider_id':None,'model':None,'updated_at':None}
  for r in rows:
   r['model_count']=len(json.loads(r.pop('models_json') or '[]'))
   r['api_key_masked']=samarkan(__import__('backend.llm_providers',fromlist=['x']).dekripsi(r.pop('api_key_enc')))
  return jsonify(items=rows,active=aktif,server_fallback=False)
 @app.post('/api/admin/llm/providers')
 @admin
 def llm_provider_create():
  from .llm_providers import enkripsi,normalisasi_endpoint,tarik_model
  b=request.get_json() or {}
  nama=(b.get('name') or '').strip();key=(b.get('api_key') or '').strip()
  if not nama or not key:return jsonify(error='Nama dan API key wajib diisi'),422
  try:url=normalisasi_endpoint(b.get('base_url'))
  except ValueError as e:return jsonify(error=str(e)),422
  models=[];import urllib.error
  if b.get('fetch_models',True):
   try:models=tarik_model(url,key)
   except urllib.error.HTTPError as e:return jsonify(error=f'Endpoint menolak ({e.code}). Periksa URL dan API key.',models=[]),422
   except Exception as e:return jsonify(error=f'Gagal mengambil daftar model: {str(e)[:140]}',models=[]),422
  pid=str(uuid.uuid4())
  with db() as c:c.execute('INSERT INTO llm_providers(id,name,base_url,api_key_enc,models_json,updated_at) VALUES(?,?,?,?,?,?)',
                           (pid,nama,url,enkripsi(key),json.dumps(models),now()))
  audit('llm_provider_create','llm',pid)
  return jsonify(id=pid,name=nama,base_url=url,model_count=len(models),models=models),201
 @app.patch('/api/admin/llm/providers/<pid>')
 @admin
 def llm_provider_update(pid):
  from .llm_providers import enkripsi,normalisasi_endpoint,tarik_model
  b=request.get_json() or {}
  with db() as c:row=c.execute('SELECT * FROM llm_providers WHERE id=?',(pid,)).fetchone()
  if not row:return jsonify(error='Penyedia tidak ditemukan'),404
  url=row['base_url']
  if b.get('base_url'):
   try:url=normalisasi_endpoint(b['base_url'])
   except ValueError as e:return jsonify(error=str(e)),422
  enc=enkripsi(b['api_key'].strip()) if b.get('api_key') else row['api_key_enc']
  with db() as c:c.execute('UPDATE llm_providers SET name=?,base_url=?,api_key_enc=?,updated_at=? WHERE id=?',
                           ((b.get('name') or row['name']).strip(),url,enc,now(),pid))
  models=json.loads(row['models_json'] or '[]')
  if b.get('refresh') or b.get('api_key') or b.get('base_url'):
   from .llm_providers import dekripsi as _dek
   try:
    models=tarik_model(url,_dek(enc))
    with db() as c:c.execute('UPDATE llm_providers SET models_json=? WHERE id=?',(json.dumps(models),pid))
   except Exception as e:return jsonify(error=f'Gagal memperbarui model: {str(e)[:140]}',models=models),422
  audit('llm_provider_update','llm',pid)
  return jsonify(id=pid,base_url=url,model_count=len(models),models=models),200
 @app.delete('/api/admin/llm/providers/<pid>')
 @admin
 def llm_provider_delete(pid):
  with db() as c:
   if not c.execute('SELECT 1 FROM llm_providers WHERE id=?',(pid,)).fetchone():return jsonify(error='Penyedia tidak ditemukan'),404
   c.execute('DELETE FROM llm_providers WHERE id=?',(pid,))
   c.execute('UPDATE llm_config SET provider_id=NULL,model=NULL,updated_at=? WHERE id=1',(now(),))
  audit('llm_provider_delete','llm',pid);return jsonify(ok=True),200
 @app.get('/api/admin/llm/providers/<pid>/models')
 @admin
 def llm_provider_models(pid):
  from .llm_providers import dekripsi,tarik_model
  with db() as c:row=c.execute('SELECT * FROM llm_providers WHERE id=?',(pid,)).fetchone()
  if not row:return jsonify(error='Penyedia tidak ditemukan'),404
  try:models=tarik_model(row['base_url'],dekripsi(row['api_key_enc']))
  except Exception as e:return jsonify(error=f'Gagal mengambil model: {str(e)[:140]}'),422
  with db() as c:c.execute('UPDATE llm_providers SET models_json=?,updated_at=? WHERE id=?',(json.dumps(models),now(),pid))
  return jsonify(items=models,count=len(models)),200
 @app.post('/api/admin/llm/active')
 @admin
 def llm_active_set():
  from .llm_providers import dekripsi,tarik_model,uji_kirim
  b=request.get_json() or {};pid=(b.get('provider_id') or '').strip();model=(b.get('model') or '').strip()
  if not pid or not model:return jsonify(error='Penyedia dan model wajib dipilih'),422
  with db() as c:row=c.execute('SELECT * FROM llm_providers WHERE id=?',(pid,)).fetchone()
  if not row:return jsonify(error='Penyedia tidak ditemukan'),404
  if b.get('fetch_models'):
   try:models=tarik_model(row['base_url'],dekripsi(row['api_key_enc']))
   except Exception as e:return jsonify(error=f'Gagal mengambil model: {str(e)[:140]}'),422
  else:models=json.loads(row['models_json'] or '[]')
  if model not in {m['id'] for m in models}:
   return jsonify(error=f'Model {model} tidak ada pada penyedia ini. Muat ulang daftar model.'),422
  try:uji=uji_kirim(row['base_url'],dekripsi(row['api_key_enc']),model)
  except Exception as e:return jsonify(error=f'Model tidak dapat menjawab: {str(e)[:140]}'),422
  with db() as c:
   c.execute('INSERT INTO llm_config(id,provider_id,model,updated_by,updated_at) VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET provider_id=?,model=?,updated_by=?,updated_at=?',
             (pid,model,user()['id'],now(),pid,model,user()['id'],now()))
  audit('llm_active_set','llm',pid)
  return jsonify(provider_id=pid,model=model,probe=uji),200
 @app.get('/api/admin/llm/active')
 @admin
 def llm_active_get():
  with db() as c:
   cfg=c.execute('SELECT * FROM llm_config WHERE id=1').fetchone()
   row=c.execute('SELECT id,name,base_url,models_json FROM llm_providers WHERE id=?',(cfg['provider_id'],)).fetchone() if cfg and cfg['provider_id'] else None
  if not cfg or not cfg['model'] or not row:return jsonify(provider_id=None,model=None,provider_name=None,pending=True),200
  return jsonify(provider_id=row['id'],provider_name=row['name'],model=cfg['model'],
                 model_count=len(json.loads(row['models_json'] or '[]')),updated_at=cfg['updated_at']),200
 def train_job(jid,stage,quick):
  with app.app_context():
   try:
    with db() as c:c.execute("UPDATE training_jobs SET status='running',progress=10 WHERE id=?",(jid,))
    r=train_stage(app.config['DATASET'],stage,app.config['ARTIFACT_DIR'],quick=quick)
    best=r['best']
    with db() as c:
     for alg,v in r['all_versions'].items():
      status='champion' if alg==best else 'candidate'
      if alg==best:c.execute("UPDATE model_versions SET status='archived' WHERE stage=? AND status='champion'",(stage,))
      c.execute('INSERT INTO model_versions(id,stage,algorithm,status,experimental,metrics,path,checksum,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(v['version'],stage,alg,status,0,json.dumps({'test':v['metrics'],'candidates':r['metrics']['candidates']}),v['path'],v['checksum'],now()))
     c.execute("UPDATE training_jobs SET status='completed',progress=100,result=? WHERE id=?",(json.dumps(r),jid))
   except Exception as e:
    with db() as c:c.execute("UPDATE training_jobs SET status='failed',error=? WHERE id=?",(str(e),jid))
 @app.post('/api/admin/training-jobs')
 @admin
 def training():
  b=request.get_json() or {};jid=str(uuid.uuid4());stage=b.get('stage','intake');
  with db() as c:c.execute('INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?)',(jid,stage,'queued',0,None,None,now()))
  threading.Thread(target=train_job,args=(jid,stage,bool((b.get('config') or {}).get('quick'))),daemon=True).start();return jsonify(id=jid,status='queued'),202
 @app.get('/api/admin/training-jobs/<jid>')
 @admin
 def training_get(jid):
  with db() as c:r=c.execute('SELECT * FROM training_jobs WHERE id=?',(jid,)).fetchone()
  return jsonify(dict(r))
 @app.get('/api/admin/training-jobs')
 @admin
 def training_list():
  with db() as c:return jsonify(items=[dict(x) for x in c.execute('SELECT * FROM training_jobs ORDER BY created_at DESC')])
 @app.delete('/api/admin/training-jobs/<jid>')
 @admin
 def training_delete(jid):
  import shutil
  with db() as c:
   job=c.execute('SELECT * FROM training_jobs WHERE id=?',(jid,)).fetchone()
   if not job:return jsonify(error='Training job not found'),404
   if job['status'] in ('queued','running'):return jsonify(error='Training yang sedang berjalan tidak dapat dihapus'),409
   result=json.loads(job['result']) if job['result'] else {};versions=[x.get('version') for x in result.get('all_versions',{}).values() if x.get('version')]
   rows=c.execute('SELECT id,path FROM model_versions WHERE id IN (%s)'%(','.join('?'*len(versions))),versions).fetchall() if versions else []
   c.execute('DELETE FROM model_versions WHERE id IN (%s)'%(','.join('?'*len(versions))),versions) if versions else None
   c.execute('DELETE FROM training_jobs WHERE id=?',(jid,))
   c.execute("UPDATE datasets SET status='ready',trained_at=NULL WHERE stage=? AND status='trained'",(job['stage'],))
  active_file=Path(app.config['ARTIFACT_DIR'])/'active.json';active=json.loads(active_file.read_text()) if active_file.exists() else {}
  active={stage:mid for stage,mid in active.items() if mid not in versions}
  if active:active_file.write_text(json.dumps(active))
  elif active_file.exists():active_file.unlink()
  for row in rows:
   path=Path(row['path'])
   if path.is_dir() and path.parent.resolve()==Path(app.config['ARTIFACT_DIR']).resolve():shutil.rmtree(path)
  audit('training_delete','training_job',jid);return jsonify(ok=True,dataset_status='ready')
 @app.get('/api/admin/model-versions')
 @admin
 def versions():
  with db() as c:rows=c.execute('SELECT * FROM model_versions ORDER BY created_at DESC').fetchall()
  items=[]
  for x in rows:d=dict(x);d['metrics']=json.loads(d['metrics']);d['experimental']=bool(d['experimental']);items.append(d)
  return jsonify(items=items)
 @app.patch('/api/admin/model-versions/<mid>')
 @admin
 def model_edit(mid):
  name=(request.get_json() or {}).get('name','').strip()
  if not name:return jsonify(error='Nama model wajib diisi'),422
  with db() as c:
   if not c.execute('SELECT 1 FROM model_versions WHERE id=?',(mid,)).fetchone():return jsonify(error='Not found'),404
   c.execute('UPDATE model_versions SET name=? WHERE id=?',(name,mid))
  audit('model_edit','model',mid);return jsonify(id=mid,name=name)
 @app.delete('/api/admin/model-versions/<mid>')
 @admin
 def model_delete(mid):
  active_file=Path(app.config['ARTIFACT_DIR'])/'active.json';active=json.loads(active_file.read_text()) if active_file.exists() else {}
  if mid in active.values():return jsonify(error='Main Model aktif tidak dapat dihapus'),409
  with db() as c:
   row=c.execute('SELECT path FROM model_versions WHERE id=?',(mid,)).fetchone()
   if not row:return jsonify(error='Not found'),404
   c.execute('DELETE FROM model_versions WHERE id=?',(mid,))
  path=Path(row['path'])
  if path.is_dir() and path.parent.resolve()==Path(app.config['ARTIFACT_DIR']).resolve():
   import shutil;shutil.rmtree(path)
  audit('model_delete','model',mid);return jsonify(ok=True)
 @app.get('/api/admin/models/active')
 @auth
 def active_models():
  active_file=Path(app.config['ARTIFACT_DIR'])/'active.json';active=json.loads(active_file.read_text()) if active_file.exists() else {}
  result={}
  with db() as c:
   for stage,mid in active.items():
    row=c.execute('SELECT * FROM model_versions WHERE id=?',(mid,)).fetchone();result[stage]=dict(row) if row else {'id':mid,'stage':stage}
  for item in result.values():
   if item.get('metrics'):item['metrics']=json.loads(item['metrics'])
  return jsonify(active=result)
 def switch_model(mid):
  with db() as c:
   r=c.execute('SELECT * FROM model_versions WHERE id=?',(mid,)).fetchone()
   if not r:return jsonify(error='Model not found'),404
   if r['status']!='champion':return jsonify(error='Hanya Champion hasil training yang dapat diimplementasikan'),409
  active=Path(app.config['ARTIFACT_DIR'])/'active.json';d=json.loads(active.read_text()) if active.exists() else {};d[r['stage']]=mid;active.write_text(json.dumps(d));audit('model_switch','model',mid);return jsonify(id=mid,status='implemented')
 @app.post('/api/admin/model-versions/<mid>/promote')
 @admin
 def promote(mid):return switch_model(mid)
 @app.post('/api/admin/model-versions/<mid>/implement')
 @admin
 def implement(mid):return switch_model(mid)
 @app.post('/api/admin/model-versions/<mid>/rollback')
 @admin
 def rollback(mid):return switch_model(mid)
 # --- Dataset management ---
 @app.get('/api/datasets')
 @auth
 def dataset_list():
  with db() as c:rows=c.execute('SELECT * FROM datasets ORDER BY created_at DESC').fetchall()
  return jsonify(items=[dict(r) for r in rows])
 @app.post('/api/datasets')
 @admin
 def dataset_upload():
  stage=request.form.get('stage','academic_update')
  if stage not in ('intake','academic_update'):return jsonify(error='Invalid stage'),422
  f=request.files.get('file')
  if not f:return jsonify(error='No file'),422
  raw=f.read();fname=f.filename or 'dataset.csv';checksum=hashlib.sha256(raw).hexdigest()
  with db() as c:
   if c.execute('SELECT 1 FROM datasets WHERE stage=? OR checksum=?',(stage,checksum)).fetchone():return jsonify(error='Dataset untuk tahap ini sudah ada. Edit atau hapus dataset lama terlebih dahulu.'),409
  # Parse to count rows/cols
  text=raw.decode('utf-8-sig')
  lines=[l for l in text.split('\n') if l.strip()]
  row_count=max(0,len(lines)-1)
  col_count=len(lines[0].split(';')) if lines else 0
  # Save file
  ds_dir=ROOT/'data/datasets';ds_dir.mkdir(parents=True,exist_ok=True)
  did=str(uuid.uuid4())
  fpath=ds_dir/f'{did}.csv'
  fpath.write_bytes(raw)
  with db() as c:c.execute('INSERT INTO datasets(id,name,stage,file_path,row_count,col_count,size_bytes,status,trained_at,uploaded_by,created_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(did,fname,stage,str(fpath),row_count,col_count,len(raw),'uploaded',None,session.get('uid'),now(),checksum))
  audit('dataset_upload','dataset',did)
  return jsonify(id=did,name=fname,stage=stage,row_count=row_count,col_count=col_count,status='uploaded'),201
 @app.get('/api/datasets/<did>')
 @auth
 def dataset_detail(did):
  with db() as c:r=c.execute('SELECT * FROM datasets WHERE id=?',(did,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  import pandas as pd
  frame=pd.read_csv(r['file_path'],sep=';').head(100)
  return jsonify(dataset=dict(r),columns=list(frame.columns),rows=frame.where(frame.notna(),None).to_dict('records'))
 @app.post('/api/datasets/<did>/preprocess')
 @admin
 def dataset_preprocess(did):
  with db() as c:r=c.execute('SELECT * FROM datasets WHERE id=?',(did,)).fetchone()
  if not r:return jsonify(error='Not found'),404
  import pandas as pd
  from .ml import UPDATE_FEATURES, CLASSES
  try:
   frame=pd.read_csv(r['file_path'],sep=';');frame.columns=[str(x).strip() for x in frame.columns];missing=[x for x in UPDATE_FEATURES+['Target'] if x not in frame.columns]
   numeric=frame[[x for x in UPDATE_FEATURES if x in frame.columns]].apply(pd.to_numeric,errors='coerce')
   report={'null_cells':int(frame.isna().sum().sum()),'invalid_cells':int(numeric.isna().sum().sum()-frame[[x for x in UPDATE_FEATURES if x in frame.columns]].isna().sum().sum()),'duplicate_rows':int(frame.duplicated().sum()),'missing_columns':missing,'class_distribution':frame['Target'].value_counts(dropna=False).to_dict() if 'Target' in frame else {},'ready':not missing and not numeric.isna().any().any() and set(frame['Target'].dropna()).issubset(set(CLASSES))}
  except Exception as e:return jsonify(error=f'Dataset tidak dapat diproses: {e}'),422
  status=r['status'] if r['status']=='trained' else ('ready' if report['ready'] else 'invalid')
  with db() as c:c.execute('UPDATE datasets SET status=? WHERE id=?',(status,did))
  audit('dataset_preprocess','dataset',did);return jsonify(id=did,status=status,preprocessing=report)
 @app.patch('/api/datasets/<did>')
 @admin
 def dataset_edit(did):
  name=(request.get_json() or {}).get('name','').strip()
  if not name:return jsonify(error='Nama dataset wajib diisi'),422
  with db() as c:
   if not c.execute('SELECT 1 FROM datasets WHERE id=?',(did,)).fetchone():return jsonify(error='Not found'),404
   c.execute('UPDATE datasets SET name=? WHERE id=?',(name,did))
  audit('dataset_edit','dataset',did);return jsonify(id=did,name=name)
 @app.delete('/api/datasets/<did>')
 @admin
 def dataset_delete(did):
  with db() as c:
   r=c.execute('SELECT * FROM datasets WHERE id=?',(did,)).fetchone()
   if not r:return jsonify(error='Not found'),404
   fpath=Path(r['file_path'])
   if fpath.exists():fpath.unlink()
   c.execute('DELETE FROM datasets WHERE id=?',(did,))
  audit('dataset_delete','dataset',did)
  return jsonify(ok=True)
 @app.post('/api/datasets/<did>/train')
 @admin
 def dataset_train(did):
  with db() as c:
   ds=c.execute('SELECT * FROM datasets WHERE id=?',(did,)).fetchone()
   if not ds:return jsonify(error='Dataset not found'),404
   if ds['status']=='trained' or ds['trained_at']:return jsonify(error='Dataset ini sudah pernah dilatih'),409
   if ds['status']!='ready':return jsonify(error='Preprocessing dataset harus lulus sebelum training'),409
   if c.execute("SELECT 1 FROM training_jobs WHERE stage=? AND status IN ('queued','running')",(ds['stage'],)).fetchone():return jsonify(error='Training untuk tahap ini sedang berjalan'),409
  stage=ds['stage'];jid=str(uuid.uuid4())
  with db() as c:c.execute('INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?)',(jid,stage,'queued',0,None,None,now()))
  def _train(jid,ds_path,stage,did):
   with app.app_context():
    try:
     with db() as c:c.execute("UPDATE training_jobs SET status='running',progress=10 WHERE id=?",(jid,))
     r=train_stage(ds_path,stage,app.config['ARTIFACT_DIR'],quick=False)
     best=r['best']
     with db() as c:
      for alg,v in r['all_versions'].items():
       st='champion' if alg==best else 'candidate'
       c.execute('INSERT INTO model_versions(id,stage,algorithm,status,experimental,metrics,path,checksum,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(v['version'],stage,alg,st,0,json.dumps({'test':v['metrics'],'candidates':r['metrics']['candidates']}),v['path'],v['checksum'],now()))
      c.execute("UPDATE training_jobs SET status='completed',progress=100,result=? WHERE id=?",(json.dumps(r),jid))
      c.execute("UPDATE datasets SET status='trained',trained_at=? WHERE id=?",(now(),did))
    except Exception as e:
     with db() as c:c.execute("UPDATE training_jobs SET status='failed',error=? WHERE id=?",(str(e),jid))
  threading.Thread(target=_train,args=(jid,ds['file_path'],stage,did),daemon=True).start()
  return jsonify(id=jid,dataset_id=did,status='queued'),202
 @app.route('/',defaults={'path':''})
 @app.route('/<path:path>',methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'])
 def spa(path):
  # Jangan menyamarkan endpoint API yang tidak ada sebagai index.html:
  # metode non-GET akan jadi 405 dan GET akan 200 HTML, dua-duanya menyesatkan.
  if path.startswith('api/'):
   return jsonify(error='Endpoint tidak ditemukan atau belum aktif di server ini',
                  error_code='api_route_missing',method=request.method,path='/'+path),404
  dist=ROOT/'frontend/dist';target=dist/path
  return send_from_directory(dist,path) if path and target.is_file() else send_from_directory(dist,'index.html')
 return app

app=create_app()
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','1426')),threaded=True)
