from pathlib import Path
from datetime import datetime,timezone
from dataclasses import dataclass,field,asdict
from enum import Enum
class Status(str,Enum):
 FOUND='found'
 EMPTY='empty'
 NOT_FOUND='not_found'
 ACCESS_DENIED='access_denied'
 CHECK_FAILED='check_failed'
 UNSUPPORTED_FORMAT='unsupported_format'
 NOT_INSPECTED='not_inspected'
 PARTIAL='partial'
 NOT_APPLICABLE='not_applicable'
@dataclass
class CheckResult:
 id:str
 title:str
 area_number:int
 locations:list=field(default_factory=list)
 findings:dict=field(default_factory=dict)
 limitations:list=field(default_factory=list)
 cleanup_available:bool=False
 def to_dict(self):return asdict(self)
class Check:
 def result(self):return CheckResult(self.id,self.title,self.area_number)
 def plan(self,context):
  r=self.result()
  r.cleanup_available=False
  r.findings={'targets':[],'requires_ollama_stop':False,'warning':None}
  return r
 def execute(self,context,plan_result,confirmed=False):
  if not confirmed:raise ValueError('Confirmation required for cleanup.')
  raise NotImplementedError('Cleanup not implemented for this checker.')
 def verify(self,context):
  return self.inspect(context)

def inspect_path(path,context,kind='file'):
 p=Path(path);r=dict(path=str(p),context=context,kind=kind,status='not_inspected',size_bytes=None,modified_at=None,date_capability='none',details={})
 try:
  if p.is_symlink():r['details']['reason']='Symlink not followed.';return r
  s=p.stat();r['modified_at']=datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat()
  if kind=='directory':
   if not p.is_dir():r['status']='unsupported_format'
   else:
    import os
    with os.scandir(p) as entries:r['status']='found' if next(entries,None) else 'empty'
  elif not p.is_file():r['status']='unsupported_format'
  else:
   r['size_bytes']=s.st_size
   with p.open('rb') as f:f.read(1)
   r['status']='found' if s.st_size else 'empty'
 except FileNotFoundError:r['status']='not_found'
 except PermissionError:r['status']='access_denied'
 except OSError:r['status']='check_failed'
 return r
