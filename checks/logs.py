import os,re,codecs
from pathlib import Path
from datetime import datetime
from .base import Check,inspect_path
STAMP=re.compile(r'^(?:time=)?["\[]?(\d{4}-\d{2}-\d{2}[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)')
class LogsCheck(Check):
 id='logs';title='Logs and destinations';area_number=3
 def inspect(self,c):
  r=self.result();directories=[]
  for a in c.accounts:
   if a.platform.startswith('win') and a.local_app_data:directories.append((a.local_app_data/'Ollama',a.label))
   elif a.platform=='darwin':directories.append((a.home/'.ollama/logs',a.label))
   else:r.locations.append(dict(path='system journal / unresolved logs',context=a.label,kind='logging_destination',status='not_inspected',details={}))
  directories.extend((p,'explicit') for p in c.log_directories)
  for base,label in directories:
   directory=inspect_path(base,label,'directory');r.locations.append(directory)
   if directory['status'] not in ('found','empty'):continue
   try:
    directory['details']['unclassified_entries']=[]
    with os.scandir(base) as entries:
     for i,e in enumerate(entries):
      if i>=c.max_entries:directory['status']='partial';break
      if '.log' in e.name.lower() or e.name.lower().endswith(('.err','.out')):r.locations.append(self.read(Path(e.path),label,c))
      else:directory['details']['unclassified_entries'].append(e.name)
   except OSError:directory['status']='check_failed'
  for p in c.redirected_logs:r.locations.append(self.read(Path(p),'explicit_redirection',c))
  for name in ('Docker logging driver','Manual terminal and unknown redirections','External log collectors'):r.locations.append(dict(path=name,context='context_not_established',kind='logging_destination',status='not_inspected',details={}))
  logs=[l for l in r.locations if l['kind']=='log_candidate'];r.findings={'log_files':len(logs),'fully_read_logs':sum(l['details'].get('full_file_read',False) for l in logs),'interaction_classification':'not_validated','today_cleanup_supported':True,'cleanup_implemented':True}
  r.limitations=['Full files are streamed from the beginning up to the stated per-file safety limit. Oversized or changing files are partial.','Timestamp parsing groups continuation lines but does not identify prompt/reply payloads. Interaction classification and cleanup remain unavailable.','Undated timestamps are treated as local only for provisional date summaries. Full conversation date coverage is not claimed.','No log text or timestamp lines are returned. Docker/journal/collector adapters remain unimplemented.']
  r.cleanup_available=len(logs)>0
  return r
 def plan(self,c,mode='all'):
  r=self.result();targets=[];mode_all=mode=='all'
  directories=[]
  for a in c.accounts:
   if a.platform.startswith('win') and a.local_app_data:directories.append((a.local_app_data/'Ollama',a.label))
   elif a.platform=='darwin':directories.append((a.home/'.ollama/logs',a.label))
  directories.extend((p,'explicit') for p in c.log_directories)
  for base,label in directories:
   try:
    if not base.is_dir():continue
    for e in base.iterdir():
     if e.is_symlink():continue
     if e.is_file() and ('.log' in e.name.lower() or e.name.lower().endswith(('.err','.out'))):
      s=e.stat()
      targets.append({'path':str(e),'context':label,'size_bytes':s.st_size,'modified_at':datetime.fromtimestamp(s.st_mtime).isoformat(),'mode':mode})
   except (OSError,PermissionError):pass
  for p in c.redirected_logs:
   try:
    if Path(p).is_file() and not Path(p).is_symlink():
     s=Path(p).stat()
     targets.append({'path':p,'context':'explicit_redirection','size_bytes':s.st_size,'modified_at':datetime.fromtimestamp(s.st_mtime).isoformat(),'mode':mode})
   except (OSError,PermissionError):pass
  r.cleanup_available=len(targets)>0
  r.findings={'targets':targets,'requires_ollama_stop':True,'warning':'Ollama should be stopped before deleting logs to avoid file locks. Delete all removes entire log files; delete today truncates at midnight.'}
  return r
 def execute(self,c,plan_result,confirmed=False):
  if not confirmed:raise ValueError('Confirmation required for cleanup.')
  results=[]
  for target in plan_result.findings['targets']:
   p=Path(target['path'])
   result={'path':target['path'],'context':target['context'],'status':'deleted','reason':None}
   try:
    if p.is_symlink():result['status']='skipped';result['reason']='Symlink not followed.'
    elif not p.is_file():result['status']='skipped';result['reason']='Not a file or does not exist.'
    else:p.unlink()
   except PermissionError:result['status']='access_denied';result['reason']='Permission denied (Ollama may be running).'
   except OSError as e:result['status']='failed';result['reason']=str(e)
   results.append(result)
  return {'results':results,'deleted':[r for r in results if r['status']=='deleted'],'failed':[r for r in results if r['status']=='failed'],'skipped':[r for r in results if r['status'] not in ('deleted','failed')]}
 def read(self,p,label,c):
  item=inspect_path(p,label,'log_candidate');d=item['details']
  if item['status'] not in ('found','empty'):return item
  try:
   before=p.stat()
   if before.st_size>c.max_log_bytes:item['status']='partial';d['reason']='File exceeds streaming safety limit; content analysis skipped.';return item
   with p.open('rb') as f:prefix=f.read(4)
   if prefix.startswith(b'\x1f\x8b'):item['status']='unsupported_format';d['reason']='Gzip candidate; decompression not implemented.';return item
   encoding='utf-32' if prefix in (codecs.BOM_UTF32_LE,codecs.BOM_UTF32_BE) else 'utf-16' if prefix.startswith((codecs.BOM_UTF16_LE,codecs.BOM_UTF16_BE)) else 'utf-8-sig'
   lines=records=continuations=orphans=today=0;first=last=None;naive=0
   # Limit individual line memory; never emit oversized log content.
   with p.open('r',encoding=encoding,errors='strict',newline=None) as f:
    while True:
     line=f.readline(c.max_read_bytes+1)
     if not line:break
     if len(line)>c.max_read_bytes:item['status']='partial';d['reason']='Oversized single line; scan stopped.';break
     lines+=1
     if '\x00' in line:raise ValueError('NUL bytes: unsupported text encoding or binary file.')
     match=STAMP.match(line);parsed=None
     if match:
      try:parsed=datetime.fromisoformat(match.group(1).replace('Z','+00:00'))
      except ValueError:pass
     if parsed:
      records+=1
      if parsed.tzinfo is None:naive+=1;parsed=parsed.astimezone()
      local=parsed.astimezone();today+=int(local.date()==datetime.now().astimezone().date())
      if first is None or parsed<first:first=parsed
      if last is None or parsed>last:last=parsed
     elif records:continuations+=1
     else:orphans+=1
   after=p.stat();stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
   if not stable:item['status']='partial';d['reason']='File changed while being read.'
   d.update(encoding=encoding,full_file_read=item['status'] in ('found','empty'),physical_lines=lines,timestamped_records=records,continuation_lines=continuations,unassigned_leading_lines=orphans,earliest_record_timestamp=first.isoformat() if first else None,latest_record_timestamp=last.isoformat() if last else None,records_dated_today=today,timestamps_without_offset=naive,interaction_classification='not_validated')
  except UnicodeError:item['status']='unsupported_format';d['reason']='Strict decoding failed; no replacement characters or guessed fallback used.'
  except ValueError as exc:item['status']='unsupported_format';d['reason']=str(exc)
  except PermissionError:item['status']='access_denied'
  except OSError:item['status']='check_failed'
  return item
