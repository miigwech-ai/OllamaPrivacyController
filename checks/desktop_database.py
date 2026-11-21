import sqlite3,time,os
from pathlib import Path
from .base import Check,inspect_path
class DesktopDatabaseCheck(Check):
 id='desktop_database';title='Desktop database';area_number=2
 def inspect(self,c):
  r=self.result();databases=[]
  for a in c.accounts:
   base=a.local_app_data/'Ollama' if a.platform.startswith('win') and a.local_app_data else a.home/'Library/Application Support/Ollama' if a.platform=='darwin' else None
   if base is None:
    r.locations.append(dict(path='No resolved desktop database path',context=a.label,kind='database',status='not_inspected',details={}));continue
   items={}
   for suffix in ('','-wal','-shm','-journal'):
    p=base/('db.sqlite'+suffix);item=inspect_path(p,a.label,'database' if not suffix else 'database_companion');items[suffix]=item;r.locations.append(item)
   db=items[''];summary={'path':db['path'],'active_rows':{},'schema_status':'not_inspected','companions':{s:items[s]['status'] for s in ('-wal','-shm','-journal')},'residual_content':'not_examined'};databases.append(summary)
   if db['status'] not in ('found','empty'):continue
   if any(items[s]['status']=='not_inspected' for s in items):summary['reason']='Symlink/unresolved companion; skipped SQLite open.';continue
   if items['-wal']['status'] not in ('not_found','empty') and items['-shm']['status']=='not_found':summary['reason']='WAL without SHM; skipped to avoid creating a companion.';continue
   conn=None
   try:
    conn=sqlite3.connect((base/'db.sqlite').absolute().as_uri()+'?mode=ro',uri=True,timeout=1);conn.execute('PRAGMA query_only=ON');deadline=time.monotonic()+3;conn.set_progress_handler(lambda:int(time.monotonic()>deadline),1000);conn.execute('BEGIN')
    names=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT ?",(c.max_entries+1,)).fetchall();schema=[]
    for (name,) in names[:c.max_entries]:
     q='"'+name.replace('"','""')+'"';columns=conn.execute('PRAGMA table_info('+q+')').fetchall();schema.append({'name':name,'columns':[{'name':v[1],'type':v[2]} for v in columns]})
     if name in ('chats','messages','attachments','tool_calls'):summary['active_rows'][name]=conn.execute('SELECT COUNT(*) FROM '+q).fetchone()[0]
    summary.update(schema_status='read',freelist_pages=conn.execute('PRAGMA freelist_count').fetchone()[0],journal_mode=conn.execute('PRAGMA journal_mode').fetchone()[0]);db['details']['schema']=schema
    if len(names)>c.max_entries:db['status']='partial'
   except sqlite3.Error:db['status']='partial';summary['schema_status']='busy_unreadable_or_unsupported'
   finally:
    if conn:conn.close()
  r.findings={'databases':databases}
  r.limitations=['Zero active rows does not establish absence of recoverable content. Free pages and WAL frames are not carved.','Read-only SQLite can take read locks and participate in WAL coordination; this is not forensic no-touch acquisition.','No checkpoints, VACUUM, settings reads, attachment contents or conversation text. Cleanup remains unavailable.']
  r.cleanup_available=any(db.get('active_rows',{}).get('chats',0)>0 or db.get('active_rows',{}).get('messages',0)>0 for db in databases)
  return r
 def plan(self,c):
  r=self.result();targets=[]
  for a in c.accounts:
   base=a.local_app_data/'Ollama' if a.platform.startswith('win') and a.local_app_data else a.home/'Library/Application Support/Ollama' if a.platform=='darwin' else None
   if base is None:continue
   db_path=base/'db.sqlite'
   try:
    if db_path.is_symlink():continue
    if not db_path.is_file():continue
    conn=sqlite3.connect(db_path.absolute().as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
     conn.execute('PRAGMA query_only=ON');deadline=time.monotonic()+10;conn.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
     conn.execute('BEGIN')
     chats=conn.execute('SELECT COUNT(*) FROM chats').fetchone()[0]
     messages=conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
     if chats>0 or messages>0:
      targets.append({'path':str(db_path),'context':a.label,'chats':chats,'messages':messages})
    finally:
     conn.close()
   except (sqlite3.Error,OSError,PermissionError):pass
  r.cleanup_available=len(targets)>0
  r.findings={'targets':targets,'requires_ollama_stop':True,'warning':'This deletes all rows from chats, messages, attachments, and tool_calls tables. WAL checkpointing is performed. Deleted content may remain in free pages; VACUUM is not automatic.'}
  return r
 def execute(self,c,plan_result,confirmed=False):
  if not confirmed:raise ValueError('Confirmation required for cleanup.')
  results=[]
  for target in plan_result.findings['targets']:
   p=Path(target['path'])
   result={'path':target['path'],'context':target['context'],'status':'deleted','reason':None,'chats_deleted':0,'messages_deleted':0}
   try:
    if p.is_symlink():result['status']='skipped';result['reason']='Symlink not followed.'
    elif not p.is_file():result['status']='skipped';result['reason']='Not a file or does not exist.'
    else:
     conn=sqlite3.connect(str(p),timeout=10)
     try:
      conn.execute('BEGIN')
      chats_before=conn.execute('SELECT COUNT(*) FROM chats').fetchone()[0]
      messages_before=conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
      conn.execute('DELETE FROM tool_calls')
      conn.execute('DELETE FROM attachments')
      conn.execute('DELETE FROM messages')
      conn.execute('DELETE FROM chats')
      conn.commit()
      conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
      result['chats_deleted']=chats_before
      result['messages_deleted']=messages_before
     finally:
      conn.close()
   except PermissionError:result['status']='access_denied';result['reason']='Permission denied (Ollama may be running).'
   except sqlite3.Error as e:result['status']='failed';result['reason']=f'SQLite error: {str(e)}'
   except OSError as e:result['status']='failed';result['reason']=str(e)
   results.append(result)
  return {'results':results,'deleted':[r for r in results if r['status']=='deleted'],'failed':[r for r in results if r['status']=='failed'],'skipped':[r for r in results if r['status'] not in ('deleted','failed')],
          'note':'Deleted rows may remain recoverable in SQLite free pages until VACUUM is run manually. WAL checkpoint was attempted after commit.'}
