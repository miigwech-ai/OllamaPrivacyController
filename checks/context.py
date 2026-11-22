from dataclasses import dataclass,field
from pathlib import Path
import os,sys
from datetime import datetime,time
import platform_paths
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
  keys=('OLLAMA_MODELS','OLLAMA_DEBUG','OLLAMA_DEBUG_LOG_REQUESTS','OLLAMA_NOHISTORY','OLLAMA_NO_CLOUD','OLLAMA_HOST');sources={}
  sources['helper_process']={'status':'read','values':{k:os.environ.get(k) for k in keys}}
  platform=sys.platform
  if platform_paths.is_windows(platform):
   for scope in ('user','machine'):
    record={'status':'unsupported','values':{k:None for k in keys}}
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
  elif platform_paths.is_macos(platform):
   record={'status':'read','values':{k:None for k in keys}}
   errors=[]
   for k in keys:
    found,value,error=platform_paths.launchctl_getenv(k)
    if error:errors.append(error)
    elif found:record['values'][k]=value
   if errors:record['status']='check_failed'
   sources['user']=record
   sources['machine']={'status':'unsupported','values':{k:None for k in keys},'note':'Machine-wide launchd environment is not inspected.'}
  else:
   for scope in ('user','machine'):
    sources[scope]={'status':'unsupported','values':{k:None for k in keys}}
  now=datetime.now().astimezone();midnight=datetime.combine(now.date(),time.min).astimezone()
  local_app_data=Path(os.environ['LOCALAPPDATA']) if platform_paths.is_windows(platform) and os.environ.get('LOCALAPPDATA') else None
  return cls([AccountContext('current_user',Path.home(),local_app_data)],sources,today_start=midnight.isoformat(),scan_started=now.isoformat())
