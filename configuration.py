"""Allowlisted, reversible current-user environment changes."""
import os,json,secrets,time,threading,plistlib,subprocess,sys,hashlib,ctypes
from pathlib import Path
import platform_paths
SETTINGS={
 'OLLAMA_DEBUG':{'label':'Debug verbosity','target':'0','choices':['0','1','2'],'impact':'0 = normal INFO logging; 1 = DEBUG; 2 = TRACE. Not a logging-off switch.'},
 'OLLAMA_DEBUG_LOG_REQUESTS':{'label':'Request dumps','target':'false','choices':['false','true'],'impact':'Disable future request dumps. Does not delete existing dumps.'},
 'OLLAMA_NOHISTORY':{'label':'Disable CLI history','target':'true','choices':['true','false'],'impact':'true disables new CLI readline history. Does not disable desktop chat storage.'},
 'OLLAMA_NO_CLOUD':{'label':'Disable cloud features','target':'true','choices':['true','false'],'impact':'Disables cloud features where supported; local client integrations may lose cloud functionality.'},
 'OLLAMA_HOST':{'label':'Listening address','target':'127.0.0.1:11434','choices':['127.0.0.1:11434'],'impact':'Loopback only. Existing LAN clients will no longer reach this server after restart.'}
}
LOCK=threading.RLock();PLANS={}
class ConfigError(Exception):pass

def _is_windows():return platform_paths.is_windows()
def _is_macos():return platform_paths.is_macos()
def _supported():return _is_windows() or _is_macos()
def _backend_name():return 'windows_registry' if _is_windows() else 'macos_launchctl' if _is_macos() else None
def _value_type():return 1 if _is_windows() else 'env'
def require_supported():
 if not _supported():raise ConfigError('Configuration writes are supported only on Windows and macOS beta.')

def _windows_snapshot(scope='user'):
 import winreg
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

def _windows_write_entries(entries,side):
 import winreg
 with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key:
  for item in entries:
   value=item[side]
   if value is None:
    try:winreg.DeleteValue(key,item['name'])
    except FileNotFoundError:pass
   else:winreg.SetValueEx(key,item['name'],0,value['type'],value['value'])

def _windows_broadcast():
 try:
  result=ctypes.c_size_t()
  ctypes.windll.user32.SendMessageTimeoutW(65535,26,0,'Environment',2,2000,ctypes.byref(result))
 except Exception:pass

def _launchctl(args):
 try:return subprocess.run([platform_paths.LAUNCHCTL,*args],capture_output=True,text=True,timeout=8)
 except (OSError,subprocess.SubprocessError):raise ConfigError('launchctl command failed.')

def _mac_getenv(name):
 found,value,error=platform_paths.launchctl_getenv(name)
 if error:raise ConfigError('Cannot read macOS launchd environment settings.')
 return found,value

def _mac_snapshot(scope='user'):
 if scope!='user':raise ConfigError('Only the user launchd environment is supported on macOS.')
 values={}
 for name in SETTINGS:
  found,value=_mac_getenv(name)
  values[name]={'value':value,'type':'env'} if found else None
 return values

def _mac_setenv(name,value):
 if value is None:_launchctl(['unsetenv',name])
 else:_launchctl(['setenv',name,value])
 found,actual=_mac_getenv(name)
 if value is None:
  if found:raise ConfigError('launchctl read-back failed for '+name+'.')
 elif not found or actual!=value:raise ConfigError('launchctl read-back failed for '+name+'.')

def _mac_write_entries(entries,side):
 for item in entries:_mac_setenv(item['name'],None if item[side] is None else item[side]['value'])

def _agent_label(name):return 'com.ollamaPrivacyController.env.'+name.lower()
def _agent_dir():return Path.home()/'Library'/'LaunchAgents'
def _agent_path(name):return _agent_dir()/(_agent_label(name)+'.plist')
def _agent_bytes(name,value):
 return plistlib.dumps({'Label':_agent_label(name),'ProgramArguments':['/bin/launchctl','setenv',name,value],'RunAtLoad':True},fmt=plistlib.FMT_XML)
def _agent_meta(data):return {'sha256':hashlib.sha256(data).hexdigest()}
def _write_agent(name,value,allow_existing_match=False):
 data=_agent_bytes(name,value);path=_agent_path(name);directory=path.parent
 if directory.is_symlink():raise ConfigError('Refusing linked LaunchAgents directory.')
 directory.mkdir(parents=True,exist_ok=True)
 if path.is_symlink() or (path.exists() and (not allow_existing_match or path.read_bytes()!=data)):
  raise ConfigError('Refusing to overwrite existing launch agent for '+name+'.')
 if path.exists():return _agent_meta(data)
 temp=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
 try:
  with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.chmod(temp,0o644);os.replace(temp,path)
 finally:
  if temp.exists():temp.unlink()
 return _agent_meta(data)
def _agent_names():
 if not _is_macos():return []
 return [name for name in SETTINGS if _agent_path(name).exists() or _agent_path(name).is_symlink()]
def _ensure_no_agents():
 if _agent_names():raise ConfigError('Existing OllamaPrivacyController launch agents found. Restore the tracked change set or remove them before applying.')
def _remove_agent_files(meta):
 verified=[]
 for name,info in meta.items():
  if name not in SETTINGS:raise ConfigError('Launch agent metadata is invalid.')
  path=_agent_path(name)
  if not path.exists() and not path.is_symlink():continue
  if path.is_symlink() or not path.is_file():raise ConfigError('Launch agent path is not a regular file.')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=info.get('sha256'):raise ConfigError('Launch agent changed since apply; not removing.')
  verified.append(path)
 for path in verified:path.unlink()
def _create_agents(changes):
 meta={};created=[]
 try:
  for item in changes:
   if item['after'] is None:continue
   meta[item['name']]=_write_agent(item['name'],item['after']['value']);created.append(item['name'])
 except Exception:
  for name in created:
   try:_remove_agent_files({name:meta[name]})
   except Exception:pass
  raise
 return meta
def _restore_agents(changes):
 meta={};created=[]
 try:
  for item in changes:
   if item['before'] is None:continue
   meta[item['name']]=_write_agent(item['name'],item['before']['value'],allow_existing_match=True);created.append(item['name'])
 except Exception:
  for name in created:
   try:_remove_agent_files({name:meta[name]})
   except Exception:pass
  raise
 return meta

def snapshot(scope='user'):
 require_supported()
 return _windows_snapshot(scope) if _is_windows() else _mac_snapshot(scope)
def write_entries(entries,side):
 if _is_windows():_windows_write_entries(entries,side)
 else:_mac_write_entries(entries,side)
def broadcast():
 if _is_windows():_windows_broadcast()
def validate_before(name,before):
 if before is None:return
 if _is_windows():
  if not isinstance(before['value'],str) or before['type'] not in (1,2):raise ConfigError('Unsupported existing registry value type for '+name)
 elif before.get('type')!='env' or not isinstance(before.get('value'),str):raise ConfigError('Unsupported existing launchd value for '+name)
def backup_path():
 path=platform_paths.config_backup_path()
 if path is None:raise ConfigError('LOCALAPPDATA is unavailable; cannot save reversible configuration metadata.')
 return path

def read_backup():
 path=backup_path()
 if not path.exists():return None
 try:
  if path.is_symlink():raise ValueError()
  data=json.loads(path.read_text(encoding='utf-8'))
  if data.get('version')!=1 or not isinstance(data.get('changes'),list):raise ValueError()
  allowed={1,2} if _is_windows() else {'env'}
  for item in data['changes']:
   if item['name'] not in SETTINGS:raise ValueError()
   for side in ('before','after'):
    val=item[side]
    if val is not None and (not isinstance(val,dict) or not isinstance(val.get('value'),str) or val.get('type') not in allowed):raise ValueError()
  agents=data.get('agents')
  if agents is not None:
   if not isinstance(agents,dict):raise ValueError()
   for name,info in agents.items():
    if name not in SETTINGS or not isinstance(info,dict) or not isinstance(info.get('sha256'),str):raise ValueError()
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
 if not _supported():return {'supported':False,'settings':[],'error':'Configuration writes are supported only on Windows and macOS beta.','platform':sys.platform,'backend':None}
 with LOCK:
  user=snapshot('user');machine_error=None;machine={}
  if _is_windows():
   try:machine=snapshot('machine')
   except ConfigError as exc:machine_error=str(exc)
  else:machine_error='Machine-wide environment is not used by the macOS launchctl backend.'
  backup=read_backup();agents=_agent_names()
  return {'supported':True,'platform':_backend_name(),'beta':_is_macos(),'machine_supported':_is_windows(),'settings':[dict(name=name,**meta,user=user[name],machine=machine.get(name)) for name,meta in SETTINGS.items()], 'machine_error':machine_error,'restore_available':bool(backup),'persistent_overrides':agents,'restart_required':bool(backup),'runtime_verification':'not_implemented','note':('Saved launchd user-session values only; app settings/server.json and running process are not inspected. Login persistence uses generated LaunchAgents and is untested beta.' if _is_macos() else 'Saved user values only; app settings/server.json and running process are not inspected.')}

def plan(body,session):
 require_supported()
 with LOCK:
  current=snapshot('user');backup=read_backup();mode=body.get('mode','apply');changes=[]
  if mode=='restore':
   if not backup:raise ConfigError('No previous configuration to restore.')
   for item in backup['changes']:
    if current[item['name']]!=item['after']:raise ConfigError('Restore conflict for '+item['name']+'. A saved value changed since apply.')
    changes.append({'name':item['name'],'before':current[item['name']],'after':item['before']})
  elif mode=='apply':
   if backup:raise ConfigError('A configuration change set is already tracked. Restore it before making another change set in this prototype.')
   if _is_macos():_ensure_no_agents()
   proposed=body.get('changes')
   if not isinstance(proposed,dict) or not proposed:raise ConfigError('No proposed changes.')
   if len(proposed)>len(SETTINGS):raise ConfigError('Too many changes.')
   for name,value in proposed.items():
    if name not in SETTINGS or value not in SETTINGS[name]['choices']:raise ConfigError('Unsupported setting or value.')
    before=current[name];validate_before(name,before);after={'value':value,'type':_value_type()}
    if before!=after:changes.append({'name':name,'before':before,'after':after})
  else:raise ConfigError('Unsupported plan mode.')
  if not changes:raise ConfigError('No changes are needed.')
  token=secrets.token_urlsafe(32)
  for old in list(PLANS):
   if PLANS[old]['expires']<time.monotonic():del PLANS[old]
  if len(PLANS)>100:PLANS.clear()
  PLANS[token]={'mode':mode,'changes':changes,'session':session,'expires':time.monotonic()+300,'backup':backup}
  return {'plan_token':token,'mode':mode,'changes':changes,'expires_in_seconds':300,'restart_required':True,'backend':_backend_name(),'persistence':'launchd_login_agents_beta' if _is_macos() else 'current_user_registry'}

def apply(body,session):
 require_supported()
 with LOCK:
  token=body.get('plan_token');p=PLANS.pop(token,None) if isinstance(token,str) else None
  if not p or p['session']!=session or p['expires']<time.monotonic():raise ConfigError('Plan expired or invalid. Review changes again.')
  if body.get('confirmed') is not True:raise ConfigError('Explicit confirmation required.')
  current=snapshot()
  if any(current[i['name']]!=i['before'] for i in p['changes']):raise ConfigError('Saved settings changed after review; create a fresh plan.')
  if read_backup()!=p['backup']:raise ConfigError('Backup state changed; review again.')
  if p['mode']=='apply':
   if _is_macos():_ensure_no_agents()
   agents={}
   try:
    save_backup({'version':1,'changes':p['changes'],'state':'pending'})
    write_entries(p['changes'],'after')
    if _is_macos():agents=_create_agents(p['changes'])
    actual=snapshot()
    if any(actual[i['name']]!=i['after'] for i in p['changes']):raise ConfigError('Configuration read-back failed.')
   except Exception:
    if _is_macos() and agents:
     try:_remove_agent_files(agents)
     except Exception:pass
    try:write_entries(p['changes'],'before')
    except Exception:raise ConfigError('Write failed and rollback was incomplete. Backup retained; inspect before further changes.')
    raise ConfigError('Write failed; rollback attempted. Backup retained for review.')
   save_backup({'version':1,'changes':p['changes'],'state':'saved','agents':agents})
   persistence='launchd_login_agents_beta'
  else:
   agents_meta=(p['backup'] or {}).get('agents',{})
   try:
    if _is_macos():
     missing=[i['name'] for i in p['changes'] if i['name'] not in agents_meta and (_agent_path(i['name']).exists() or _agent_path(i['name']).is_symlink())]
     if missing:raise ConfigError('Launch agent metadata is missing for '+', '.join(missing)+'.')
     _remove_agent_files({name:agents_meta[name] for name in agents_meta if name in {i['name'] for i in p['changes']}})
    write_entries(p['changes'],'after')
    actual=snapshot()
    if any(actual[i['name']]!=i['after'] for i in p['changes']):raise ConfigError('Configuration read-back failed.')
    backup_path().unlink()
   except Exception as exc:
    original=str(exc)
    try:
     if _is_macos():_restore_agents(p['changes'])
     write_entries(p['changes'],'before')
    except Exception:raise ConfigError('Restore failed ('+original+'); rollback incomplete. Backup retained; inspect before further changes.')
    raise ConfigError('Restore failed ('+original+'); rollback attempted. Backup retained for review.')
   persistence='removed'
  broadcast()
  return {'saved':True,'mode':p['mode'],'changed':[i['name'] for i in p['changes']],'restart_required':True,'runtime_verified':False,'backend':_backend_name(),'persistence':persistence,'persistent_overrides':sorted(agents) if p['mode']=='apply' and _is_macos() else [],'message':('Saved launchd values verified. Restart Ollama manually; login persistence is beta/untested and running settings are not verified.' if _is_macos() else 'Saved values verified. Restart Ollama manually; current running settings are not verified.')}
