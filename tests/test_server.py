import json
from unittest.mock import Mock
import pytest

@pytest.mark.parametrize("path", ["/api/configuration", "/api/desktop-settings", "/api/scan", "/api/ollama/status"])
def test_read_routes(invoke, path):
    call, _ = invoke(path)
    assert call.args[0] == 200

@pytest.mark.parametrize("headers", [
    {"Host": "evil.example"}, {"Origin": "https://evil.example"},
    {"Sec-Fetch-Site": "cross-site"}, {"Host": None}
])
def test_read_access_denied(invoke, backend, headers):
    call, _ = invoke("/api/desktop-settings", headers=headers)
    assert call.args[0] == 403
    backend[3].inspect.assert_not_called()

def auth(server):
    return {"Origin": "http://127.0.0.1:8765", "X-OPC-CSRF": server.CSRF,
            "Content-Type": "application/json", "Content-Length": "2"}

@pytest.mark.parametrize("change", [{"Origin": None}, {"X-OPC-CSRF": "wrong"}, {"Origin": "https://evil.example"}])
def test_write_requires_origin_and_token(invoke, backend, change):
    headers = auth(backend[1]); headers.update(change)
    call, _ = invoke("/api/configuration/apply", "POST", b"{}", headers)
    assert call.args[0] == 403
    backend[2].apply.assert_not_called()

@pytest.mark.parametrize("path,attribute", [("/api/configuration/plan", "plan"), ("/api/configuration/apply", "apply")])
def test_write_dispatch(invoke, backend, path, attribute):
    call, _ = invoke(path, "POST", b"{}", auth(backend[1]))
    assert call.args[0] == 200
    getattr(backend[2], attribute).assert_called_once_with({}, backend[1].CSRF)

@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b'"x"', b"\xff"])
def test_invalid_json(invoke, backend, body):
    headers=auth(backend[1]); headers["Content-Length"]=str(len(body))
    call, _=invoke("/api/configuration/plan", "POST", body, headers)
    assert call.args[0] == 400
    backend[2].plan.assert_not_called()

@pytest.mark.parametrize("length", ["0", "-1", "16385"])
def test_length_limit(invoke, backend, length):
    headers=auth(backend[1]); headers["Content-Length"]=length
    call, _=invoke("/api/configuration/plan", "POST", b"{}", headers)
    assert call.args[0] == 413

def test_non_json_rejected(invoke, backend):
    headers=auth(backend[1]); headers["Content-Type"]="text/plain"
    assert invoke("/api/configuration/plan", "POST", b"{}", headers)[0].args[0] == 415

def test_transfer_encoding_rejected(invoke, backend):
    headers=auth(backend[1]); headers["Transfer-Encoding"]="chunked"
    assert invoke("/api/configuration/plan", "POST", b"{}", headers)[0].args[0] == 400

@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS"])
def test_unsupported_methods(invoke, method):
    assert invoke("/api/configuration", method)[0].args[0] == 405

def test_unknown_route(invoke):
    assert invoke("/unknown")[0].args[0] == 404

def test_scan_lock(invoke, backend):
    server=backend[1]; server.SCAN_LOCK.acquire()
    try:
        assert invoke("/api/scan")[0].args[0] == 409
    finally:
        server.SCAN_LOCK.release()

def test_checker_failure_is_partial(invoke, backend):
    bad=Mock(); bad.id="logs"; bad.title="Logs"; bad.inspect.side_effect=RuntimeError("private")
    good=Mock(); good.inspect.return_value.to_dict.return_value={"id":"cli_history", "findings":{}}
    backend[1].CHECKS=[bad,good]
    call,_=invoke("/api/scan")
    assert call.args[0] == 200
    data=call.args[1]
    assert len(data["checks"]) == 2
    assert data["checks"][0]["error"] == "RuntimeError"
    assert "private" not in json.dumps(data)
    assert data["cleanup_available"] is False
    assert not backend[1].SCAN_LOCK.locked()

def test_desktop_exception_sanitized(invoke, backend):
    backend[3].inspect.side_effect=RuntimeError("sensitive path")
    call,_=invoke("/api/desktop-settings")
    assert call.args[0] == 500
    assert "sensitive" not in json.dumps(call.args[1])

def test_config_error_mapping(invoke, backend):
    backend[2].inspect.side_effect=backend[2].ConfigError("fixture error")
    assert invoke("/api/configuration")[0].args[0] == 400
    backend[2].plan.side_effect=backend[2].ConfigError("stale")
    assert invoke("/api/configuration/plan", "POST", b"{}", auth(backend[1]))[0].args[0] == 409

def test_static_registration(backend):
    assert backend[1].STATIC["/script/desktop_settings.js"][0] == "script/desktop_settings.js"

@pytest.mark.parametrize("path", ["/api/configuration", "/api/desktop-settings"])
def test_head_flag(invoke,path):
    call,_=invoke(path,"HEAD")
    assert call.kwargs["head"] is True

def test_response_headers_and_head(backend):
    import io
    h=object.__new__(backend[0].Handler)
    h.send_response=Mock(); h.send_header=Mock(); h.end_headers=Mock(); h.wfile=io.BytesIO()
    backend[1].Handler.send(h,200,{"ok":True},head=True)
    assert h.wfile.getvalue()==b""
    headers=dict(c.args for c in h.send_header.call_args_list)
    assert headers["Cache-Control"]=="no-store"
    assert headers["X-Content-Type-Options"]=="nosniff"
    assert headers["X-Frame-Options"]=="DENY"


class _FakePlan:
    def __init__(self, targets):
        self.findings = {"targets": targets}
        self.cleanup_available = bool(targets)
    def to_dict(self):
        return {"id": "cli_history", "cleanup_available": self.cleanup_available, "findings": self.findings}


class _FakeChecker:
    id = "cli_history"
    title = "CLI prompt history"
    def __init__(self, targets):
        self._targets = targets
    def plan(self, context):
        return _FakePlan(self._targets)
    def execute(self, context, plan, confirmed=False):
        return {"deleted": [], "failed": []}
    def verify(self, context):
        result = Mock()
        result.to_dict.return_value = {}
        return result


def _cleanup_plan(invoke, backend, targets=None):
    if targets is None:
        targets = [{"path": "C:/fake/history", "context": "test", "size_bytes": 3}]
    backend[1].CHECKS.append(_FakeChecker(targets))
    call, _ = invoke("/api/cleanup/plan")
    assert call.args[0] == 200
    return call.args[1]["plan_token"]


def _execute(invoke, backend, body):
    import json as _json
    payload = _json.dumps(body).encode()
    headers = auth(backend[1])
    headers["Content-Length"] = str(len(payload))
    return invoke("/api/cleanup/execute", "POST", payload, headers)


def test_cleanup_execute_requires_plan_token(invoke, backend):
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": True})
    assert call.args[0] == 400


def test_cleanup_execute_rejects_unknown_token(invoke, backend):
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": True, "plan_token": "bogus"})
    assert call.args[0] == 409


def test_cleanup_execute_happy_path(invoke, backend):
    token = _cleanup_plan(invoke, backend)
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": True, "plan_token": token})
    assert call.args[0] == 200


def test_cleanup_execute_rejects_expired_token(invoke, backend, monkeypatch):
    import time
    token = _cleanup_plan(invoke, backend)
    wrapper = backend[0]
    wrapper.CLEANUP_PLANS[token]["expires"] = time.monotonic() - 1
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": True, "plan_token": token})
    assert call.args[0] == 409


def test_cleanup_execute_rejects_changed_targets(invoke, backend):
    targets = [{"path": "C:/fake/history", "context": "test", "size_bytes": 3}]
    checker = _FakeChecker(targets)
    backend[1].CHECKS.append(checker)
    call, _ = invoke("/api/cleanup/plan")
    token = call.args[1]["plan_token"]
    checker._targets = [{"path": "C:/fake/history", "context": "test", "size_bytes": 99}]
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": True, "plan_token": token})
    assert call.args[0] == 409


def test_cleanup_execute_rejects_unconfirmed(invoke, backend):
    token = _cleanup_plan(invoke, backend)
    call, _ = _execute(invoke, backend, {"checker_id": "cli_history", "confirmed": False, "plan_token": token})
    assert call.args[0] == 400
