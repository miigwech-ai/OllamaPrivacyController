"""Existing app plus desktop settings, cleanup, and fixed-command test runner.
Run: py server_with_settings.py (Windows) or python3 server_with_settings.py (macOS)
"""
from pathlib import Path
import importlib.util
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import desktop_settings
from checks.context import ScanContext
import model_cleanup

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('opc_existing_server', ROOT / 'server.py')
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)
existing.STATIC['/script/desktop_settings.js'] = ('script/desktop_settings.js', 'text/javascript')
existing.STATIC['/script/tests.js'] = ('script/tests.js', 'text/javascript')
existing.STATIC['/script/cleanup.js'] = ('script/cleanup.js', 'text/javascript')
existing.STATIC['/script/model_cleanup.js'] = ('script/model_cleanup.js', 'text/javascript')
TEST_LOCK = threading.Lock()
CLEANUP_LOCK = threading.Lock()
CLEANUP_PLANS = {}
CLEANUP_PLAN_TTL = 300


def parse_report(path):
    if not path.is_file():
        return [], None
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Test report exceeded the 10 MB limit.')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unexpected XML declaration in test report.')
    root = ET.fromstring(raw)
    if root.tag not in ('testsuite', 'testsuites'):
        raise ValueError('Unrecognized test report.')
    cases = []
    for suite in (s for s in root.iter() if s.tag in ('testsuite', 'testsuites')):
        # Direct children avoid counting nested suites twice.
        for item in suite:
            if item.tag not in ('testcase', 'error', 'failure'):
                continue
            problem = item if item.tag != 'testcase' else next((c for c in item if c.tag in ('failure', 'error', 'skipped')), None)
            state = 'passed' if problem is None else {'failure':'failed','error':'error','skipped':'skipped'}[problem.tag]
            detail = '' if problem is None else (problem.get('message', '') + '\n' + ''.join(problem.itertext())).strip()
            cases.append({'name':item.get('name', 'Suite-level problem'), 'group':item.get('classname', suite.get('name', '')), 'status':state, 'time':item.get('time', '—'), 'detail':detail[:12000]})
    counts = {key:sum(c['status'] == state for c in cases) for key,state in [('passed','passed'),('failed','failed'),('errors','error'),('skipped','skipped')]}
    return cases, counts


def run_tests(suite):
    start = time.monotonic()
    result = {'suite':suite, 'status':'error', 'message':'', 'cases':[], 'counts':None, 'output':''}
    try:
        with tempfile.TemporaryDirectory(prefix='opc-tests-') as temp:
            report = Path(temp) / 'results.xml'
            if suite == 'python':
                targets = [ROOT/'tests'/'test_desktop_reader.py', ROOT/'tests'/'test_server.py', ROOT/'tests'/'test_cleanup.py', ROOT/'tests'/'test_macos.py']
                if not all(p.is_file() for p in targets):
                    raise ValueError('Python test package is missing. Extract it into the project folder first.')
                command = [sys.executable, '-m', 'pytest', *map(str, targets), '-q', '--color=no', '--junitxml='+str(report)]
            else:
                node = shutil.which('node')
                if not node:
                    raise ValueError('Node.js was not found. Restart the helper after installing Node.js.')
                targets = sorted((ROOT/'tests-js').glob('*.test.cjs'))
                if not targets:
                    raise ValueError('JavaScript test files were not found in tests-js.')
                command = [node, '--test', '--test-reporter=junit', '--test-reporter-destination='+str(report), *map(str, targets)]
            env = os.environ.copy()
            # Keep unrelated global pytest plugins and startup hooks out of these runs.
            for key in ('PYTEST_ADDOPTS','PYTEST_PLUGINS','NODE_OPTIONS'):
                env.pop(key, None)
            env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
            with (Path(temp)/'output.txt').open('w+b') as output:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, shell=False, start_new_session=os.name != 'nt')
                timed_out = False
                try:
                    returncode = process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    # Terminate the runner tree on Windows; no shell or user command interpolation.
                    if os.name == 'nt':
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    else:
                        import signal
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except (ProcessLookupError, PermissionError):
                            pass
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except (ProcessLookupError, PermissionError):
                                pass
                    if process.poll() is None:
                        process.kill()
                    returncode = process.wait(timeout=10)
                output.seek(0,2)
                size = output.tell()
                output.seek(max(0,size-24000))
                result['output'] = output.read().decode('utf-8','replace')
            cases, counts = parse_report(report)
            result.update(cases=cases, counts=counts, exit_code=returncode)
            if timed_out:
                result.update(status='error', message='Test runner exceeded the two-minute limit and was stopped. Results may be incomplete.')
            elif returncode != 0:
                result.update(status='failed', message='The suite did not pass. Expand the results or runner output for details.')
            elif not cases:
                result.update(status='error', message='Runner exited successfully but returned no test cases.')
            elif counts['failed'] or counts['errors']:
                result.update(status='failed', message='The report contains failures or errors.')
            else:
                skipped = counts['skipped']
                result.update(status='completed_with_skips' if skipped else 'passed', message=f"{counts['passed']} passed; {skipped} skipped.")
    except Exception as exc:
        result.update(status='error', message=str(exc))
    result['duration_seconds'] = round(time.monotonic()-start, 2)
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    return result


class Handler(existing.Handler):
    def read(self, head=False):
        path = urlsplit(self.path).path
        if path not in ('/api/desktop-settings', '/api/tests/session', '/api/cleanup/plan', '/api/model-cleanup/plan'):
            return super().read(head)
        if not self.allowed():
            return
        try:
            if path == '/api/tests/session':
                data = {'csrf_token':existing.CSRF}
            elif path == '/api/desktop-settings':
                data = desktop_settings.inspect()
            elif path == '/api/cleanup/plan':
                if not CLEANUP_LOCK.acquire(False):
                    self.send(409, {'error':'Cleanup operation already in progress.'}, head=head); return
                try:
                    context = ScanContext.current()
                    plans = []
                    for checker in existing.CHECKS:
                        # Exclude saved_models from general cleanup - use separate model cleanup
                        if checker.id == 'saved_models':
                            continue
                        try:
                            plan = checker.plan(context)
                            plans.append(plan.to_dict())
                        except Exception as exc:
                            plans.append({'id':checker.id,'title':checker.title,'error':type(exc).__name__,'cleanup_available':False,'findings':{}})
                    now = time.monotonic()
                    for old in list(CLEANUP_PLANS):
                        if CLEANUP_PLANS[old]['expires'] < now:
                            del CLEANUP_PLANS[old]
                    if len(CLEANUP_PLANS) > 20:
                        CLEANUP_PLANS.clear()
                    token = secrets.token_urlsafe(32)
                    CLEANUP_PLANS[token] = {'plans':{p.get('id'):p for p in plans},'session':existing.CSRF,'expires':now+CLEANUP_PLAN_TTL}
                    data = {'plans':plans,'plan_token':token,'plan_expires_in_seconds':CLEANUP_PLAN_TTL,'csrf_token':existing.CSRF}
                finally:
                    CLEANUP_LOCK.release()
            elif path == '/api/model-cleanup/plan':
                result = model_cleanup.plan_model_cleanup()
                if result.get('status') == 409:
                    self.send(409, {'error':result['error']}, head=head); return
                data = result['plan']
                data['csrf_token'] = existing.CSRF
            self.send(200, data, head=head)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {'error':'Local inspection failed. No settings were changed.'}, head=head)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == '/api/tests/run':
            return self.handle_tests_run()
        elif path == '/api/cleanup/execute':
            return self.handle_cleanup_execute()
        elif path == '/api/model-cleanup/execute':
            return self.handle_model_cleanup_execute()
        return super().do_POST()

    def handle_tests_run(self):
        if not self.allowed(True):
            return
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                self.send(415, {'error':'JSON required.'}); return
            if self.headers.get('Transfer-Encoding'):
                self.send(400, {'error':'Transfer encoding unsupported.'}); return
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 1024:
                self.send(413, {'error':'Invalid body length.'}); return
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or set(body) != {'suite'} or body['suite'] not in ('python','js'):
                self.send(400, {'error':'Choose python or js; custom commands are not accepted.'}); return
            if not TEST_LOCK.acquire(False):
                self.send(409, {'error':'A test suite is already running. Wait for it to finish.'}); return
            try:
                result = run_tests(body['suite'])
            finally:
                TEST_LOCK.release()
            self.send(200, result)
        except (ValueError, UnicodeError):
            self.send(400, {'error':'Invalid JSON test request.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {'error':'Test runner request failed.'})

    def handle_cleanup_execute(self):
        if not self.allowed(True):
            return
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                self.send(415, {'error':'JSON required.'}); return
            if self.headers.get('Transfer-Encoding'):
                self.send(400, {'error':'Transfer encoding unsupported.'}); return
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 16384:
                self.send(413, {'error':'Invalid body length.'}); return
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not {'checker_id','confirmed','plan_token'} <= set(body):
                self.send(400, {'error':'checker_id, plan_token and confirmed required.'}); return
            if body['confirmed'] is not True:
                self.send(400, {'error':'Confirmation required.'}); return
            # Reject saved_models in general cleanup - use separate model cleanup endpoint
            if body['checker_id'] == 'saved_models':
                self.send(400, {'error':'Model cleanup must use /api/model-cleanup/execute endpoint.'}); return
            token = body['plan_token']
            if not isinstance(token, str):
                self.send(400, {'error':'Invalid plan token.'}); return
            entry = CLEANUP_PLANS.get(token)
            if not entry or entry['session'] != existing.CSRF or entry['expires'] < time.monotonic():
                self.send(409, {'error':'Cleanup plan expired or invalid. Generate a new plan.'}); return
            if not CLEANUP_LOCK.acquire(False):
                self.send(409, {'error':'Cleanup operation already in progress.'}); return
            try:
                context = ScanContext.current()
                checker = next((c for c in existing.CHECKS if c.id == body['checker_id']), None)
                stored = entry['plans'].get(body['checker_id'])
                if not checker or not stored or not stored.get('cleanup_available'):
                    self.send(404, {'error':'Checker not found or no reviewed targets.'}); return
                fresh = checker.plan(context)
                if json.dumps(fresh.findings.get('targets',[]), sort_keys=True) != json.dumps(stored.get('findings',{}).get('targets',[]), sort_keys=True):
                    self.send(409, {'error':'Cleanup targets changed since the reviewed plan. Generate a new plan.'}); return
                result = checker.execute(context, fresh, confirmed=True)
                verification = checker.verify(context)
                data = {'result':result,'verification':verification.to_dict()}
                self.send(200, data)
            finally:
                CLEANUP_LOCK.release()
        except (ValueError, UnicodeError):
            self.send(400, {'error':'Invalid request.'})
        except Exception as exc:
            self.send(500, {'error':f'Cleanup failed: {str(exc)}'})

    def handle_model_cleanup_execute(self):
        if not self.allowed(True):
            return
        try:
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                self.send(415, {'error':'JSON required.'}); return
            if self.headers.get('Transfer-Encoding'):
                self.send(400, {'error':'Transfer encoding unsupported.'}); return
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 16384:
                self.send(413, {'error':'Invalid body length.'}); return
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or 'confirmed' not in body:
                self.send(400, {'error':'confirmed required.'}); return
            if not body['confirmed']:
                self.send(400, {'error':'Confirmation required.'}); return
            result = model_cleanup.execute_model_cleanup(confirmed=True)
            if result.get('status') == 503:
                self.send(503, {'error':result['error']}); return
            if result.get('status') == 400:
                self.send(400, {'error':result['error']}); return
            verification = model_cleanup.verify_model_cleanup()
            data = {'result':result, 'verification':verification}
            self.send(200, data)
        except (ValueError, UnicodeError):
            self.send(400, {'error':'Invalid request.'})
        except Exception as exc:
            self.send(500, {'error':f'Model cleanup failed: {str(exc)}'})


if __name__ == '__main__':
    try:
        server = ThreadingHTTPServer((existing.HOST, existing.PORT), Handler)
    except OSError as exc:
        raise SystemExit(f'Stop the previous helper first: {exc}')
    print(f'Open http://{existing.HOST}:{existing.PORT} — settings and test runner')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
