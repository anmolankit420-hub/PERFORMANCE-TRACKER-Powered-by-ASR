import os, sqlite3
from pathlib import Path
from datetime import date, datetime
import pandas as pd
from flask import Flask, request, redirect, url_for, session, render_template_string, jsonify, send_from_directory
from werkzeug.utils import secure_filename

BASE=Path(__file__).parent; DB=BASE/'oyo.db'; UP=BASE/'uploads'; SOB=UP/'sob'; PERF=UP/'performance'
for p in (UP,SOB,PERF): p.mkdir(parents=True,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me')
ADMIN_USER=os.getenv('ADMIN_USER','admin'); ADMIN_PASS=os.getenv('ADMIN_PASS','admin123')

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init():
 c=conn(); c.executescript('''
 CREATE TABLE IF NOT EXISTS agents(cz_id TEXT PRIMARY KEY,name TEXT,tl TEXT,qa TEXT,am TEXT,shift TEXT,status TEXT);
 CREATE TABLE IF NOT EXISTS sob(id INTEGER PRIMARY KEY,data_date TEXT,interval TEXT,cz_id TEXT,d_day TEXT,d1 TEXT,d2 TEXT,mtd TEXT,source TEXT,uploaded_at TEXT);
 CREATE TABLE IF NOT EXISTS perf(id INTEGER PRIMARY KEY,data_date TEXT,cz_id TEXT,booking TEXT,poc TEXT,realization TEXT,productivity TEXT,prepay TEXT,aht TEXT,brn TEXT,cr TEXT,sob TEXT,total_booking TEXT,total_poc TEXT,total_prepay TEXT,urn TEXT,source TEXT,uploaded_at TEXT);
 CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY,file_type TEXT,file_name TEXT,stored_name TEXT,data_date TEXT,interval TEXT,uploaded_at TEXT);
 '''); c.commit(); c.close()

def clean(x):
 s='' if x is None else str(x).strip(); return '' if s.lower() in ('nan','none','nat') else s

def norm(x): return clean(x).lower().replace('_',' ').replace('-',' ').replace('%',' pct ').strip()

def col(df,names):
 ns=[norm(x) for x in names]
 for x in df.columns:
  if norm(x) in ns:return x
 for x in df.columns:
  z=norm(x)
  if any(n in z for n in ns):return x
 return None

def tables(path):
 if Path(path).suffix.lower()=='.csv': return [pd.read_csv(path,dtype=str)]
 return list(pd.read_excel(path,sheet_name=None,dtype=str).values())

def czcol(df): return col(df,['cz id','czid','associate cz id','employee cz id'])

def up_agent(c,cz,row,kind):
 name=clean(row.get(col(row.to_frame().T,['name','names','agent name','employee name']),'') if False else '')
 # metadata is handled separately in import functions

def upsert(c,cz,name='',tl='',qa='',am='',shift='',status='Active'):
 old=c.execute('select * from agents where cz_id=?',(cz,)).fetchone()
 if old:
  vals=[name or old['name'],tl or old['tl'],qa or old['qa'],am or old['am'],shift or old['shift'],status or old['status']]
  c.execute('update agents set name=?,tl=?,qa=?,am=?,shift=?,status=? where cz_id=?',(*vals,cz))
 else:c.execute('insert into agents values(?,?,?,?,?,?,?)',(cz,name,tl,qa,am,shift,status))

def import_file(path,kind,source,data_date,interval=''):
 c=conn(); now=datetime.now().isoformat(timespec='seconds'); count=0
 for df in tables(path):
  if df is None or df.empty: continue
  df.columns=[clean(x) for x in df.columns]; zc=czcol(df)
  if not zc: continue
  nc=col(df,['name','names','agent name','employee name']); tlc=col(df,['tl','team leader','supervisor']); qac=col(df,['qa','quality analyst']); amc=col(df,['am','assistant manager','manager']); shc=col(df,['shift','timing']); stc=col(df,['status','state']); dc=col(df,['date','data date','report date']); ic=col(df,['interval','time','slot'])
  for _,r in df.iterrows():
   cz=clean(r.get(zc,''));
   if not cz: continue
   d=clean(r.get(dc,'')) if dc else data_date
   try:d=pd.to_datetime(d).date().isoformat()
   except: d=d or data_date
   upsert(c,cz,clean(r.get(nc,'')) if nc else '',clean(r.get(tlc,'')) if tlc else '',clean(r.get(qac,'')) if qac else '',clean(r.get(amc,'')) if amc else '',clean(r.get(shc,'')) if shc else '',clean(r.get(stc,'')) if stc else 'Active')
   if kind=='SOB':
    c.execute('insert into sob(data_date,interval,cz_id,d_day,d1,d2,mtd,source,uploaded_at) values(?,?,?,?,?,?,?,?,?)',(d,clean(r.get(ic,'')) if ic else interval,cz,clean(r.get(col(df,['d day','d-day','sob d-day']),'')),clean(r.get(col(df,['d 1','d-1','d1','yesterday']),'')),clean(r.get(col(df,['d 2','d-2','d2']),'')),clean(r.get(col(df,['mtd','mtd sob','sob utilization','sob utilization pct']),'')),source,now))
   else:
    def v(names):
     cc=col(df,names); return clean(r.get(cc,'')) if cc else ''
    c.execute('''insert into perf(data_date,cz_id,booking,poc,realization,productivity,prepay,aht,brn,cr,sob,total_booking,total_poc,total_prepay,urn,source,uploaded_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(d,cz,v(['booking','booking pct','booking%']),v(['poc','poc pct','poc%']),v(['realization','realization pct','realization%']),v(['productivity']),v(['prepay','prepay pct','prepay%']),v(['aht']),v(['brn 4 rz','brn-4-rz','brn-4-rz pct']),v(['c r','c*r','cr','c r pct']),v(['sob utilization','sob utilization pct','sob pct','sob']),v(['total booking','total bookings','bookings']),v(['total poc','poc count']),v(['total prepay','prepay count']),v(['urn']),source,now))
   count+=1
 c.commit();c.close();return count

def admin(): return session.get('admin') is True

def agent_data(cz,d):
 c=conn(); a=c.execute('select * from agents where cz_id=?',(cz,)).fetchone(); s=c.execute('select * from sob where cz_id=? and data_date=? order by id desc limit 1',(cz,d)).fetchone(); p=c.execute('select * from perf where cz_id=? and data_date=? order by id desc limit 1',(cz,d)).fetchone(); sh=c.execute('select data_date,interval,d_day,d1,d2,mtd from sob where cz_id=? order by data_date desc,id desc limit 30',(cz,)).fetchall(); ph=c.execute('select data_date,booking,poc,realization,productivity,prepay,aht,sob from perf where cz_id=? order by data_date desc,id desc limit 30',(cz,)).fetchall(); c.close(); return (dict(a) if a else None,dict(s) if s else None,dict(p) if p else None,[dict(x) for x in sh],[dict(x) for x in ph])

BASE_HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title><style>body{margin:0;font-family:Arial;background:#f5f5f5;color:#171717}.top{height:62px;background:#fff;border-bottom:1px solid #ddd;display:flex;align-items:center;justify-content:space-between;padding:0 5%}.brand{font-size:19px}.dot{display:inline-block;width:12px;height:12px;background:#e4002b;border-radius:50%;margin-right:7px}nav a{margin-left:18px;color:#333;text-decoration:none;font-size:13px}.wrap{max-width:1200px;margin:auto;padding:28px 18px 60px}.hero{background:#151515;color:#fff;border-radius:16px;padding:36px;margin-bottom:18px}.hero h1{margin:6px 0}.red{color:#e4002b}.muted{color:#777}.card,.kpi,.stat{background:#fff;border:1px solid #e1e1e1;border-radius:13px;padding:18px}.search{display:flex;gap:8px}.search input,input,select{padding:11px;border:1px solid #ccc;border-radius:8px;width:100%;box-sizing:border-box}button,.btn{background:#e4002b;color:#fff;border:0;border-radius:8px;padding:11px 15px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.two{grid-template-columns:repeat(2,1fr)}.kpi span,.stat span{font-size:12px;color:#777}.kpi b,.stat b{display:block;font-size:23px;margin-top:8px}.profile{display:flex;gap:18px;align-items:center}.avatar{width:58px;height:58px;border-radius:50%;background:#e4002b;color:white;display:grid;place-items:center;font-size:24px;font-weight:bold}.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-left:auto}.meta span{font-size:12px;color:#777}.meta b{display:block;color:#222;margin-bottom:3px}.section{margin-top:25px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px;border-bottom:1px solid #eee;text-align:left;white-space:nowrap}th{font-size:10px;text-transform:uppercase;background:#fafafa}.table{overflow:auto}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.upload{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}.small{font-size:11px}.danger{background:#222}.flash{padding:10px;background:#ffe7ec;margin-bottom:12px;border-radius:8px}@media(max-width:800px){.grid,.stats{grid-template-columns:repeat(2,1fr)}.upload{grid-template-columns:1fr}.meta{grid-template-columns:repeat(2,1fr);width:100%;margin:0}.profile{flex-wrap:wrap}}@media(max-width:500px){.grid,.stats{grid-template-columns:1fr}.search{flex-direction:column}.top{padding:0 12px}nav a{margin-left:8px}}</style></head><body><header class="top"><div class="brand"><i class="dot"></i>OYO <b>Performance Hub</b></div><nav><a href="/">Agent Portal</a><a href="/admin">Admin</a></nav></header><div class="wrap">{% with m=get_flashed_messages() %}{% for x in m %}<div class="flash">{{x}}</div>{% endfor %}{% endwith %}{{body|safe}}</div></body></html>'''

def page(body,title='OYO Performance Hub'): return render_template_string(BASE_HTML,title=title,body=body)

@app.route('/')
def home(): return page('''<div class="hero"><div class="red">OYO TEAM</div><h1>Agent Performance Portal</h1><p class="muted" style="color:#ccc">Enter CZ ID to check SOB and complete KPI performance.</p></div><div class="card"><form action="/agent" method="get"><label>CZ ID</label><div class="search"><input name="cz_id" placeholder="Enter CZ ID" required autofocus><button>View Performance</button></div></form></div>''')

@app.route('/agent')
def agent():
 cz=request.args.get('cz_id','').strip(); d=request.args.get('date','') or date.today().isoformat(); a,s,p,sh,ph=agent_data(cz,d) if cz else (None,None,None,[],[])
 if not cz: return redirect('/')
 body=render_template_string('''<div style="display:flex;justify-content:space-between;gap:15px;align-items:end;flex-wrap:wrap"><div><div class="red">AGENT PORTAL</div><h1>Performance Dashboard</h1></div><form action="/agent" method="get"><input type="hidden" name="cz_id" value="{{cz}}"><label>Date</label><input type="date" name="date" value="{{d}}"><button>Check Date</button></form></div>{% if not a %}<div class="card" style="margin-top:20px">No agent found for CZ ID <b>{{cz}}</b>.</div>{% else %}<div class="card profile section"><div class="avatar">{{a.name[:1]|upper or 'A'}}</div><div><h2>{{a.name or 'Agent'}}</h2><span>{{a.cz_id}}</span></div><div class="meta"><span><b>TL</b>{{a.tl or '-'}}</span><span><b>QA</b>{{a.qa or '-'}}</span><span><b>AM</b>{{a.am or '-'}}</span><span><b>Shift</b>{{a.shift or '-'}}</span></div></div><h2 class="section">SOB Utilization</h2><div class="grid"><div class="kpi"><span>D-Day</span><b>{{s.d_day if s else '-'}}</b></div><div class="kpi"><span>D-1 Day</span><b>{{s.d1 if s else '-'}}</b></div><div class="kpi"><span>D-2 Day</span><b>{{s.d2 if s else '-'}}</b></div><div class="kpi"><span>MTD</span><b>{{s.mtd if s else '-'}}</b></div></div><p class="muted small">Selected date: {{d}}</p><h2 class="section">Overall Performance</h2><div class="grid">{% for label,key in [('Booking %','booking'),('POC %','poc'),('Realization %','realization'),('Productivity','productivity'),('Prepay %','prepay'),('AHT','aht'),('BRN-4-RZ %','brn'),('C*R %','cr'),('SOB Utilization','sob'),('Total Booking','total_booking'),('Total POC','total_poc'),('Total Prepay','total_prepay')] %}<div class="kpi"><span>{{label}}</span><b>{{p[key] if p else '-'}}</b></div>{% endfor %}</div><div class="card section"><h2>SOB History</h2><div class="table"><table><tr><th>Date</th><th>Interval</th><th>D-Day</th><th>D-1</th><th>D-2</th><th>MTD</th></tr>{% for r in sh %}<tr><td>{{r.data_date}}</td><td>{{r.interval or '-'}}</td><td>{{r.d_day or '-'}}</td><td>{{r.d1 or '-'}}</td><td>{{r.d2 or '-'}}</td><td>{{r.mtd or '-'}}</td></tr>{% endfor %}</table></div></div><div class="card section"><h2>Performance History</h2><div class="table"><table><tr><th>Date</th><th>Booking</th><th>POC</th><th>Realization</th><th>Productivity</th><th>Prepay</th><th>AHT</th><th>SOB</th></tr>{% for r in ph %}<tr><td>{{r.data_date}}</td><td>{{r.booking}}</td><td>{{r.poc}}</td><td>{{r.realization}}</td><td>{{r.productivity}}</td><td>{{r.prepay}}</td><td>{{r.aht}}</td><td>{{r.sob}}</td></tr>{% endfor %}</table></div></div>{% endif %}''',cz=cz,d=d,a=a,s=s,p=p,sh=sh,ph=ph)
 return page(body,'Agent Performance')

@app.route('/admin/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  if request.form.get('username')==ADMIN_USER and request.form.get('password')==ADMIN_PASS: session['admin']=True; return redirect('/admin')
  return page('<div class="card"><h1>Invalid login</h1><a class="btn" href="/admin/login">Try again</a></div>','Admin Login')
 return page('<div class="card" style="max-width:420px;margin:50px auto"><div class="red">SECURE ACCESS</div><h1>Admin Login</h1><form method="post"><label>Username</label><input name="username" required><label>Password</label><input name="password" type="password" required><br><br><button>Login</button></form><p class="muted small">Default: admin / admin123</p></div>','Admin Login')

@app.route('/admin/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/admin')
def dashboard():
 if not admin(): return redirect('/admin/login')
 c=conn(); stats=[c.execute('select count(*) from agents').fetchone()[0],c.execute("select count(*) from agents where lower(status)!='inactive'").fetchone()[0],c.execute("select count(*) from files where file_type='SOB'").fetchone()[0],c.execute("select count(*) from files where file_type='PERFORMANCE'").fetchone()[0]]; fs=c.execute('select * from files order by id desc').fetchall(); ag=c.execute('select * from agents order by name').fetchall(); c.close()
 body=render_template_string('''<div style="display:flex;justify-content:space-between"><div><div class="red">ADMIN CONTROL</div><h1>OYO Performance Hub</h1></div><a class="btn danger" href="/admin/logout">Logout</a></div><div class="stats section">{% for x in [('Total Agents',stats[0]),('Active Agents',stats[1]),('SOB Files',stats[2]),('Performance Files',stats[3])] %}<div class="stat"><span>{{x[0]}}</span><b>{{x[1]}}</b></div>{% endfor %}</div><div class="upload section"><div class="card"><h2>SOB Interval Upload</h2><form id="sf" enctype="multipart/form-data"><label>Data Date</label><input type="date" name="data_date" value="{{today}}" required><label>Interval</label><input name="interval" placeholder="e.g. 11:00 AM"><label>Excel/CSV</label><input type="file" name="file" accept=".xlsx,.xls,.csv" required><br><br><button>Upload SOB</button></form></div><div class="card"><h2>Agent Performance Upload</h2><form id="pf" enctype="multipart/form-data"><label>Data Date</label><input type="date" name="data_date" value="{{today}}" required><label>Excel/CSV</label><input type="file" name="file" accept=".xlsx,.xls,.csv" required><br><br><button>Upload Performance</button></form></div></div><div class="card section"><h2>Uploaded Files</h2><div class="table"><table><tr><th>Type</th><th>File</th><th>Date</th><th>Interval</th><th>Uploaded</th><th>Action</th></tr>{% for f in fs %}<tr><td>{{f.file_type}}</td><td>{{f.file_name}}</td><td>{{f.data_date}}</td><td>{{f.interval or '-'}}</td><td>{{f.uploaded_at}}</td><td><a class="btn" href="/download/{{f.file_type}}/{{f.stored_name}}">Download</a> <button class="danger" onclick="delFile({{f.id}})">Delete</button></td></tr>{% endfor %}</table></div></div><div class="card section"><h2>Agents</h2><div class="table"><table><tr><th>CZ ID</th><th>Name</th><th>TL</th><th>QA</th><th>AM</th><th>Shift</th><th>Status</th><th>Action</th></tr>{% for a in ag %}<tr><td>{{a.cz_id}}</td><td>{{a.name}}</td><td>{{a.tl}}</td><td>{{a.qa}}</td><td>{{a.am}}</td><td>{{a.shift}}</td><td>{{a.status}}</td><td><button onclick="status('{{a.cz_id}}','{{'Inactive' if a.status|lower!='inactive' else 'Active'}}')">{{'Deactivate' if a.status|lower!='inactive' else 'Activate'}}</button></td></tr>{% endfor %}</table></div></div><script>async function upload(id,url){document.getElementById(id).onsubmit=async e=>{e.preventDefault();let r=await fetch(url,{method:'POST',body:new FormData(e.target)});let j=await r.json();alert(j.message||j.error);if(j.success)location.reload()}}upload('sf','/admin/upload/sob');upload('pf','/admin/upload/performance');async function delFile(id){if(confirm('Delete file and imported data?')){let r=await fetch('/admin/file/'+id,{method:'DELETE'});let j=await r.json();if(j.success)location.reload();else alert(j.error)}}async function status(cz,s){let r=await fetch('/admin/status/'+encodeURIComponent(cz),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:s})});let j=await r.json();if(j.success)location.reload()}</script>''',stats=stats,fs=fs,ag=ag,today=date.today().isoformat())
 return page(body,'Admin Dashboard')

@app.route('/admin/upload/<kind>',methods=['POST'])
def upload(kind):
 if not admin(): return jsonify(success=False,error='Unauthorized'),401
 f=request.files.get('file'); dd=request.form.get('data_date') or date.today().isoformat(); interval=request.form.get('interval','')
 if not f or Path(f.filename).suffix.lower() not in {'.xlsx','.xls','.csv'}: return jsonify(success=False,error='Select XLSX/XLS/CSV'),400
 name=secure_filename(f.filename); typ='SOB' if kind=='sob' else 'PERFORMANCE'; folder=SOB if typ=='SOB' else PERF; stored=datetime.now().strftime('%Y%m%d_%H%M%S_')+name; path=folder/stored; f.save(path)
 try:n=import_file(path,typ,name,dd,interval)
 except Exception as e:
  path.unlink(missing_ok=True); return jsonify(success=False,error=str(e)),400
 c=conn();c.execute('insert into files(file_type,file_name,stored_name,data_date,interval,uploaded_at) values(?,?,?,?,?,?)',(typ,name,stored,dd,interval,datetime.now().isoformat(timespec='seconds')));c.commit();c.close();return jsonify(success=True,message=f'{typ} uploaded. {n} rows imported.')

@app.route('/admin/file/<int:i>',methods=['DELETE'])
def delfile(i):
 if not admin(): return jsonify(success=False,error='Unauthorized'),401
 c=conn();f=c.execute('select * from files where id=?',(i,)).fetchone()
 if not f:return jsonify(success=False,error='Not found'),404
 folder=SOB if f['file_type']=='SOB' else PERF;(folder/f['stored_name']).unlink(missing_ok=True)
 table='sob' if f['file_type']=='SOB' else 'perf';c.execute(f'delete from {table} where source=?',(f['file_name'],));c.execute('delete from files where id=?',(i,));c.commit();c.close();return jsonify(success=True)

@app.route('/admin/status/<cz>',methods=['POST'])
def status(cz):
 if not admin(): return jsonify(success=False,error='Unauthorized'),401
 s=request.json.get('status','Active');c=conn();c.execute('update agents set status=? where cz_id=?',(s,cz));c.commit();c.close();return jsonify(success=True)

@app.route('/download/<typ>/<name>')
def download(typ,name):
 if not admin():return 'Unauthorized',401
 return send_from_directory(SOB if typ=='SOB' else PERF,name,as_attachment=True)

if __name__=='__main__': init(); app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)))
