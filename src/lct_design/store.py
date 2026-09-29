import json,sqlite3,time,uuid
from pathlib import Path

class JobStore:
    def __init__(self,root:Path):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'jobs.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT,created REAL,updated REAL,cancelled INTEGER,payload TEXT,result TEXT,error TEXT,stage TEXT)')
    def connect(self):
        db=sqlite3.connect(self.db,timeout=15);db.row_factory=sqlite3.Row;return db
    def decode(self,row):
        if row is None: raise KeyError('Job not found')
        item=dict(row);item['payload']=json.loads(item['payload']);item['result']=json.loads(item['result']) if item['result'] else None;item['cancelled']=bool(item['cancelled']);return item
    def create(self,payload):
        id=uuid.uuid4().hex;now=time.time()
        with self.connect() as db: db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(id,'queued',now,now,0,json.dumps(payload,ensure_ascii=False),None,None,'В очереди'))
        return self.get(id)
    def get(self,id):
        with self.connect() as db: return self.decode(db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())
    def list(self):
        with self.connect() as db: return [self.decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 30')]
    def update(self,id,**values):
        allowed={'status','stage','result','error'}
        if not set(values)<=allowed: raise ValueError('Invalid job update')
        if 'result' in values: values['result']=json.dumps(values['result'],ensure_ascii=False)
        values['updated']=time.time()
        with self.connect() as db: db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),id))
    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM jobs WHERE status='queued' AND cancelled=0 ORDER BY created LIMIT 1").fetchone()
            if row is None:return None
            db.execute("UPDATE jobs SET status='running',stage='Подготовка',updated=? WHERE id=?",(time.time(),row['id']))
            id=row['id']
        return self.get(id)
    def cancel(self,id):
        with self.connect() as db:
            db.execute("UPDATE jobs SET cancelled=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=?",(id,))
    def recover(self):
        with self.connect() as db: db.execute("UPDATE jobs SET status='interrupted',stage='Прервано перезапуском' WHERE status='running'")
