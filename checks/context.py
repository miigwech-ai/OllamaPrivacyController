from dataclasses import dataclass,field
from pathlib import Path
import os,sys
from datetime import datetime,time
@dataclass
class AccountContext:
 label:str
 home:Path
 local_app_data:Path|None=None
 platform:str=field(default_factory=lambda:sys.platform)
@dataclass
class ScanContext:
 accounts:list
 environment_sources:dict
 model_directories:list=field(default_factory=list)
 log_directories:list=field(default_factory=list)
 redirected_logs:list=field(default_factory=list)
 model_source_paths:list=field(default_factory=list)
 unresolved_contexts:list=field(default_factory=list)
 max_entries:int=3000
 max_read_bytes:int=2*1024*1024
 max_log_bytes:int=64*1024*1024
 today_start:str=''
 scan_started:str=''
 running_state:str='not_inspected'
 @classmethod
 def current(cls):
  keys=('OLLAMA_MODELS','OLLAMA_DEBUG','OLLAMA_NOHISTORY','OLLAMA_DEBUG_LOG_REQUESTS');sources={}
  sources['helper_process']={'status':'read','values':{k:os.environ.get(k) for k in keys}}
  for scope in ('user','machine'):
   record={'status':'unsupported','values':{k:None for k in keys}}
   if os.name=='nt':
    import winreg
    hive,path=(winreg.HKEY_CURRENT_USER,'Environment') if scope=='user' else (winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')
    try:
     with winreg.OpenKey(hive,path) as handle:
      record['status']='read'
      for k in keys:
       try:record['values'][k]=str(winreg.QueryValueEx(handle,k)[0])
       except FileNotFoundError:pass
    except FileNotFoundError:record['status']='not_found'
    except PermissionError:record['status']='access_denied'
    except OSError:record['status']='check_failed'
   sources[scope]=record
  now=datetime.now().astimezone();midnight=datetime.combine(now.date(),time.min).astimezone()
  return cls([AccountContext('current_user',Path.home(),Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else None)],sources,today_start=midnight.isoformat(),scan_started=now.isoformat())
