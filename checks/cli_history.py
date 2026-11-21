from .base import Check,inspect_path
from pathlib import Path
from datetime import datetime
class CliHistoryCheck(Check):
 id='cli_history';title='CLI prompt history';area_number=1
 def inspect(self,c):
  r=self.result();found=0
  for a in c.accounts:
   p=a.home/'.ollama/history';item=inspect_path(p,a.label);r.locations.append(item)
   if item['status'] not in ('found','empty'):continue
   found+=1
   try:
    with p.open('rb') as f:raw=f.read(c.max_read_bytes+1)
    truncated=len(raw)>c.max_read_bytes;raw=raw[:c.max_read_bytes]
    # Never interpret arbitrary UTF-8 lines as proven individual prompts.
    text=raw.decode('utf-8-sig');lines=text.splitlines()
    item['details']={'format':'utf8_line_storage_candidate','physical_lines':len(lines),'full_file_read':not truncated,'entry_boundaries':'not_proven','timestamp_capability':'no_supported_per_entry_timestamp_format','all_history_clear_candidate':not truncated,'today_cleanup_supported':False}
    if '\x00' in text:item['status']='unsupported_format';item['details']['reason']='NUL bytes in text candidate.'
    elif truncated:item['status']='partial'
   except UnicodeError:item['status']='unsupported_format';item['details']['reason']='Not valid UTF-8; no fallback format assumed.'
   except OSError:item['status']='check_failed'
  r.findings={'history_files_found':found,'today_cleanup_supported':False,'cleanup_implemented':True}
  r.limitations=['Line storage was inspected, not certified as individual prompt records. No history text is returned.','No supported per-entry dates; file modification times are never used as prompt dates.','Only supplied accounts are inspected; active writers and other containers are not discovered.']
  r.cleanup_available=found>0
  return r
 def plan(self,c):
  r=self.result();targets=[]
  for a in c.accounts:
   p=a.home/'.ollama/history'
   try:
    if p.is_symlink():continue
    if not p.is_file():continue
    s=p.stat()
    targets.append({'path':str(p),'context':a.label,'size_bytes':s.st_size,'modified_at':datetime.fromtimestamp(s.st_mtime).isoformat()})
   except (OSError,PermissionError):pass
  r.cleanup_available=len(targets)>0
  r.findings={'targets':targets,'requires_ollama_stop':False,'warning':'This deletes the entire history file for each account. No per-entry deletion is available.'}
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
   except PermissionError:result['status']='access_denied';result['reason']='Permission denied.'
   except OSError as e:result['status']='failed';result['reason']=str(e)
   results.append(result)
  return {'results':results,'deleted':[r for r in results if r['status']=='deleted'],'failed':[r for r in results if r['status']=='failed'],'skipped':[r for r in results if r['status'] not in ('deleted','failed')]}
