"""Local checker UI plus reviewed, reversible user environment configuration."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import build_opener,ProxyHandler,HTTPRedirectHandler,Request
from datetime import datetime,timezone
import json,threading,secrets
from checks import CHECKS
from checks.context import ScanContext
import configuration
ROOT=Path(__file__).resolve().parent;HOST='127.0.0.1';PORT=8765
HOSTS={f'127.0.0.1:{PORT}',f'localhost:{PORT}'};ORIGINS={'http://'+h for h in HOSTS};SCAN_LOCK=threading.Lock();CSRF=secrets.token_urlsafe(32)
STATIC={'/':('index.html','text/html'),'/index.html':('index.html','text/html'),'/script/app.js':('script/app.js','text/javascript'),'/script/configuration.js':('script/configuration.js','text/javascript')}
# BEGIN LOCAL THEME ASSETS
STATIC['/css/bulma/bulma.min.css'] = ('css/bulma/css/bulma.min.css', 'text/css')
STATIC['/css/themes.css'] = ('css/themes.css', 'text/css')
STATIC['/script/theme.js'] = ('script/theme.js', 'text/javascript')
# END LOCAL THEME ASSETS
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):return None
OPENER=build_opener(ProxyHandler({}),NoRedirect())
def connection():
 result={'connected':False,'version':None,'error':None}
 try:
  with OPENER.open(Request('http://127.0.0.1:11434/api/version'),timeout=4) as response:raw=response.read(65537)
  if len(raw)>65536:raise ValueError()
  version=json.loads(raw).get('version')
  if not isinstance(version,str) or not version or len(version)>200:raise ValueError()
  result.update(connected=True,version=version)
 except Exception:result['error']='Local Ollama version check failed.'
 return result
class Handler(BaseHTTPRequestHandler):
 def send(self,status,data,mime='application/json',head=False):
  raw=data if isinstance(data,bytes) else json.dumps(data).encode()
  self.send_response(status)
  for k,v in [('Content-Type',mime+'; charset=utf-8'),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','no-referrer')]:self.send_header(k,v)
  self.end_headers()
  if not head:self.wfile.write(raw)
 def allowed(self,write=False):
  origin=self.headers.get('Origin')
  ok=self.headers.get('Host') in HOSTS and (origin is None or origin in ORIGINS) and self.headers.get('Sec-Fetch-Site')!='cross-site'
  if write:ok=ok and origin in ORIGINS and secrets.compare_digest(self.headers.get('X-OPC-CSRF',''),CSRF)
  if not ok:self.send(403,{'error':'Local same-origin access and valid session token required.'})
  return ok
 def do_GET(self):self.read()
 def do_HEAD(self):self.read(True)
 def read(self,head=False):
  if not self.allowed():return
  try:
   path=urlsplit(self.path).path
   if path=='/api/configuration':
    data=configuration.inspect();data['csrf_token']=CSRF;self.send(200,data,head=head)
   elif path in ('/api/scan','/api/ollama/inspection'):
    if not SCAN_LOCK.acquire(False):self.send(409,{'error':'Scan already running.'},head=head);return
    try:
     context=ScanContext.current();checks=[]
     for checker in CHECKS:
      try:checks.append(checker.inspect(context).to_dict())
      except Exception as exc:checks.append({'id':checker.id,'title':checker.title,'error':type(exc).__name__,'locations':[],'findings':{},'limitations':['Checker failed.']})
     data={'checks':checks,'connection':connection(),'inspected_at':datetime.now(timezone.utc).isoformat(),'cleanup_available':False}
    finally:SCAN_LOCK.release()
    self.send(200,data,head=head)
   elif path=='/api/ollama/status':self.send(200,connection(),head=head)
   elif path in STATIC:
    relative,mime=STATIC[path];p=ROOT/relative
    try:p.resolve().relative_to(ROOT);raw=p.read_bytes()
    except (ValueError,OSError):self.send(404,{'error':'UI file missing.'},head=head);return
    self.send(200,raw,mime,head)
   else:self.send(404,{'error':'Not found.'},head=head)
  except configuration.ConfigError as exc:self.send(400,{'error':str(exc)},head=head)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception:self.send(500,{'error':'Helper error. Inspect saved settings before retrying.'},head=head)
 def do_POST(self):
  if not self.allowed(True):return
  try:
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.send(415,{'error':'JSON required.'});return
   if self.headers.get('Transfer-Encoding'):self.send(400,{'error':'Transfer encoding unsupported.'});return
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=16384:self.send(413,{'error':'Invalid body length.'});return
   self.connection.settimeout(10);body=json.loads(self.rfile.read(length))
   if not isinstance(body,dict):raise ValueError()
   path=urlsplit(self.path).path
   if path=='/api/configuration/plan':data=configuration.plan(body,CSRF)
   elif path=='/api/configuration/apply':data=configuration.apply(body,CSRF)
   else:self.send(404,{'error':'Not found.'});return
   self.send(200,data)
  except configuration.ConfigError as exc:self.send(409,{'error':str(exc)})
  except (ValueError,UnicodeError):self.send(400,{'error':'Invalid JSON request.'})
  except Exception:self.send(500,{'error':'Configuration operation failed. Refresh and inspect; do not assume no changes occurred.'})
 def reject(self):
  if self.allowed():self.send(405,{'error':'Method not allowed.'})
 do_PUT=reject
 do_PATCH=reject
 do_DELETE=reject
 do_OPTIONS=reject
 def log_message(self,*a):pass
if __name__=='__main__':
 try:server=ThreadingHTTPServer((HOST,PORT),Handler)
 except OSError as exc:raise SystemExit(str(exc))
 print(f'Open http://{HOST}:{PORT} — configuration requires review; no cleanup or automatic restart')
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
