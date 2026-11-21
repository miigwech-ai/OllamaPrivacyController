import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def backend(monkeypatch):
    config = types.ModuleType("configuration")
    config.ConfigError = type("ConfigError", (Exception,), {})
    config.inspect = Mock(return_value={"supported": True, "settings": []})
    config.plan = Mock(return_value={"plan_token": "fixture", "changes": []})
    config.apply = Mock(return_value={"message": "fixture only"})
    checks = types.ModuleType("checks")
    checks.CHECKS = []
    context = types.ModuleType("checks.context")
    context.ScanContext = Mock()
    desktop = types.ModuleType("desktop_settings")
    desktop.inspect = Mock(return_value={"connected": True, "settings": [], "note": "fixture"})
    for name, mod in [("configuration", config), ("checks", checks), ("checks.context", context), ("desktop_settings", desktop)]:
        monkeypatch.setitem(sys.modules, name, mod)
    wrapper = load("test_wrapper", ROOT / "server_with_settings.py")
    server = wrapper.existing
    monkeypatch.setattr(server, "connection", Mock(return_value={"connected": False, "version": None}))
    return wrapper, server, config, desktop

@pytest.fixture
def invoke(backend):
    import io
    from email.message import Message
    wrapper, server, config, desktop = backend
    def run(path, method="GET", body=b"", headers=None):
        h = object.__new__(wrapper.Handler)
        h.path = path
        h.headers = Message()
        defaults = {"Host": "127.0.0.1:8765"}
        defaults.update(headers or {})
        for k, v in defaults.items():
            if v is not None:
                h.headers[k] = v
        h.rfile = io.BytesIO(body)
        h.connection = Mock()
        h.send = Mock()
        getattr(h, "do_" + method)()
        assert h.send.call_count == 1
        return h.send.call_args, h
    return run
