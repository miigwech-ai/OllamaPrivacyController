"""Allowlisted, reversible current-user Windows environment changes only."""
import os,json,secrets,time,threading,ctypes
from pathlib import Path
SETTINGS={
 'OLLAMA_DEBUG':{'label':'Debug verbosity','target':'0','choices':['0','1','2'],'impact':'0 = normal INFO logging; 1 = DEBUG; 2 = TRACE. Not a logging-off switch.'},
 'OLLAMA_DEBUG_LOG_REQUESTS':{'label':'Request dumps','target':'false','choices':['false','true'],'impact':'Disable future request dumps. Does not delete existing dumps.'},
 'OLLAMA_NOHISTORY':{'label':'Disable CLI history','target':'true','choices':['true','false'],'impact':'true disables new CLI readline history. Does not disable desktop chat storage.'},
 'OLLAMA_NO_CLOUD':{'label':'Disable cloud features','target':'true','choices':['true','false'],'impact':'Disables cloud features where supported; local client integrations may lose cloud functionality.'},
 'OLLAMA_HOST':{'label':'Listening address','target':'127.0.0.1:11434','choices':['127.0.0.1:11434'],'impact':'Loopback only. Existing LAN clients will no longer reach this server after restart.'}
}
LOCK=threading.RLock();PLANS={}
class ConfigError(Exception):pass

def require_windows():
 if os.name!='nt':raise ConfigError('Configuration writes are supported only on Windows.')

def snapshot(scope='user'):
 require_windows();import winreg
 hive,path=(winreg.HKEY_CURRENT_USER,'Environment') if scope=='user' else (winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')
 values={name:None for name in SETTINGS}
 try:
  with winreg.OpenKey(hive,path,0,winreg.KEY_READ) as key:
   for name in SETTINGS:
    try:
     value,kind=winreg.QueryValueEx(key,name)
     values[name]={'value':value,'type':kind}
    except FileNotFoundError:pass
 except FileNotFoundError:pass
 except OSError:raise ConfigError('Cannot read '+scope+' Windows environment settings.')
 return values

def backup_path():
 base=os.environ.get('LOCALAPPDATA')
 if not base:raise ConfigError('LOCALAPPDATA is unavailable; cannot save reversible configuration metadata.')
 return Path(base)/'OllamaPrivacyController'/'configuration-backup.json'

def read_backup():
 path=backup_path()
 if not path.exists():return None
 try:
  if path.is_symlink():raise ValueError()
  data=json.loads(path.read_text(encoding='utf-8'))
  if data.get('version')!=1 or not isinstance(data.get('changes'),list):raise ValueError()
  for item in data['changes']:
   if item['name'] not in SETTINGS:raise ValueError()
   for side in ('before','after'):
    val=item[side]
    if val is not None and (not isinstance(val,dict) or not isinstance(val.get('value'),str) or val.get('type') not in (1,2)):raise ValueError()
  return data
 except (OSError,ValueError,KeyError,TypeError):raise ConfigError('Existing configuration backup is invalid or unreadable. No changes allowed.')

def save_backup(data):
 path=backup_path();path.parent.mkdir(parents=True,exist_ok=True)
 if path.parent.is_symlink() or path.is_symlink():raise ConfigError('Refusing linked backup path.')
 temp=path.with_name('backup-'+secrets.token_hex(8)+'.tmp')
 try:
  with temp.open('x',encoding='utf-8') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
  os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()

def inspect():
 if os.name!='nt':return {'supported':False,'settings':[],'error':'Windows-only configuration implementation.'}
 with LOCK:
  user=snapshot();machine_error=None
  try:machine=snapshot('machine')
  except ConfigError as exc:machine={};machine_error=str(exc)
  backup=read_backup()
  return {'supported':True,'settings':[dict(name=name,**meta,user=user[name],machine=machine.get(name)) for name,meta in SETTINGS.items()], 'machine_error':machine_error,'restore_available':bool(backup),'restart_required':bool(backup),'runtime_verification':'not_implemented','note':'Saved user values only; app settings/server.json and running process are not inspected.'}

def plan(body,session):
 require_windows()
 with LOCK:
  current=snapshot();backup=read_backup();mode=body.get('mode','apply');changes=[]
  if mode=='restore':
   if not backup:raise ConfigError('No previous configuration to restore.')
   for item in backup['changes']:
    if current[item['name']]!=item['after']:raise ConfigError('Restore conflict for '+item['name']+'. A saved value changed since apply.')
    changes.append({'name':item['name'],'before':current[item['name']],'after':item['before']})
  elif mode=='apply':
   if backup:raise ConfigError('A configuration change set is already tracked. Restore it before making another change set in this prototype.')
   proposed=body.get('changes')
   if not isinstance(proposed,dict) or not proposed:raise ConfigError('No proposed changes.')
   if len(proposed)>len(SETTINGS):raise ConfigError('Too many changes.')
   for name,value in proposed.items():
    if name not in SETTINGS or value not in SETTINGS[name]['choices']:raise ConfigError('Unsupported setting or value.')
    before=current[name]
    if before is not None and (not isinstance(before['value'],str) or before['type'] not in (1,2)):raise ConfigError('Unsupported existing registry value type for '+name)
    after={'value':value,'type':1}
    if before!=after:changes.append({'name':name,'before':before,'after':after})
  else:raise ConfigError('Unsupported plan mode.')
  if not changes:raise ConfigError('No changes are needed.')
  token=secrets.token_urlsafe(32)
  for old in list(PLANS):
   if PLANS[old]['expires']<time.monotonic():del PLANS[old]
  if len(PLANS)>100:PLANS.clear()
  PLANS[token]={'mode':mode,'changes':changes,'session':session,'expires':time.monotonic()+300,'backup':backup}
  return {'plan_token':token,'mode':mode,'changes':changes,'expires_in_seconds':300,'restart_required':True}

def write_entries(entries,side):
 import winreg
 with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key:
  for item in entries:
   value=item[side]
   if value is None:
    try:winreg.DeleteValue(key,item['name'])
    except FileNotFoundError:pass
   else:winreg.SetValueEx(key,item['name'],0,value['type'],value['value'])

def broadcast():
 try:
  result=ctypes.c_size_t()
  ctypes.windll.user32.SendMessageTimeoutW(65535,26,0,'Environment',2,2000,ctypes.byref(result))
 except Exception:pass

def apply(body,session):
 require_windows()
 with LOCK:
  token=body.get('plan_token');p=PLANS.pop(token,None) if isinstance(token,str) else None
  if not p or p['session']!=session or p['expires']<time.monotonic():raise ConfigError('Plan expired or invalid. Review changes again.')
  if body.get('confirmed') is not True:raise ConfigError('Explicit confirmation required.')
  current=snapshot()
  if any(current[i['name']]!=i['before'] for i in p['changes']):raise ConfigError('Saved settings changed after review; create a fresh plan.')
  if read_backup()!=p['backup']:raise ConfigError('Backup state changed; review again.')
  if p['mode']=='apply':save_backup({'version':1,'changes':p['changes'],'state':'pending'})
  try:
   write_entries(p['changes'],'after');actual=snapshot()
   if any(actual[i['name']]!=i['after'] for i in p['changes']):raise ConfigError('Registry read-back failed.')
  except Exception:
   try:write_entries(p['changes'],'before')
   except Exception:raise ConfigError('Write failed and rollback was incomplete. Backup retained; inspect before further changes.')
   raise ConfigError('Write failed; rollback attempted. Backup retained for review.')
  if p['mode']=='apply':save_backup({'version':1,'changes':p['changes'],'state':'saved'})
  else:backup_path().unlink()
  broadcast()
  return {'saved':True,'mode':p['mode'],'changed':[i['name'] for i in p['changes']],'restart_required':True,'runtime_verified':False,'message':'Saved values verified. Restart Ollama manually; current running settings are not verified.'}
