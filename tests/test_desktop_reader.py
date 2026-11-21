import hashlib
import json
import sqlite3
import types
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
from contextlib import closing
from conftest import ROOT, load

@pytest.fixture
def reader(tmp_path,monkeypatch):
    home=tmp_path/"home";home.mkdir()
    local=tmp_path/"local";app=local/"Ollama";app.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA",str(local))
    monkeypatch.setenv("USERPROFILE",str(home));monkeypatch.setenv("HOME",str(home))
    monkeypatch.delenv("OLLAMA_NO_CLOUD",raising=False)
    monkeypatch.setattr(Path,"home",classmethod(lambda cls:home))
    # Never access the real Windows registry, including read paths.
    registry=types.ModuleType("winreg")
    registry.HKEY_CURRENT_USER=1;registry.HKEY_LOCAL_MACHINE=2
    registry.OpenKey=Mock(side_effect=FileNotFoundError)
    monkeypatch.setitem(sys.modules,"winreg",registry)
    import socket
    monkeypatch.setattr(socket,"create_connection",Mock(side_effect=AssertionError("Network forbidden")))
    path=ROOT/"desktop_settings.py"
    if not path.exists():
        pytest.skip("desktop_settings.py was not supplied; add your current local file")
    module=load("reader_under_test",path)
    db=app/"db.sqlite"
    with closing(sqlite3.connect(db)) as c, c:
        c.executescript("CREATE TABLE users(name TEXT,plan TEXT); CREATE TABLE settings(id INTEGER,auto_update_enabled INTEGER,expose INTEGER,models TEXT,context_length INTEGER); INSERT INTO settings VALUES(1,0,0,'C:/fixture/models',0); CREATE TABLE messages(content TEXT); INSERT INTO messages VALUES('PRIVATE_SENTINEL');")
    return module,app,home,db

def row(result,label):
    return next(r for r in result["settings"] if r["label"]==label)

def test_contract_and_no_chat_content(reader):
    result=reader[0].inspect()
    assert len(result["settings"])==6
    assert len({r["label"] for r in result["settings"]})==6
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    for r in result["settings"]:
        assert {"label","value","status","reason","source"} <= r.keys()

def test_empty_cache_not_signed_out(reader):
    r=row(reader[0].inspect(),"Sign in")
    assert r["authentication_status"]=="not_verified"
    assert "not proof of sign-out" in r["value"]

def test_cached_account_not_live_verified(reader):
    with sqlite3.connect(reader[3]) as c:c.execute("INSERT INTO users VALUES('Fixture','free')")
    r=row(reader[0].inspect(),"Sign in")
    assert "Fixture" in r["value"]
    assert r["authentication_status"]=="not_verified"

@pytest.mark.parametrize("value",[0,None,8192,-1])
def test_raw_context_preserved(reader,value):
    with sqlite3.connect(reader[3]) as c:c.execute("UPDATE settings SET context_length=?",(value,))
    r=row(reader[0].inspect(),"Context length")
    assert r["raw_value"]==value
    if value==-1:assert r["status"]=="could_not_read"
    else:assert r["effective_value_verified"] is False

def test_missing_database_partial_result(reader):
    reader[3].unlink()
    result=reader[0].inspect()
    assert len(result["settings"])==6
    assert row(result,"Context length")["status"]=="could_not_read"

def test_corrupt_database(reader):
    reader[3].write_bytes(b"not sqlite")
    assert row(reader[0].inspect(),"Sign in")["status"]=="could_not_read"

def test_missing_column(reader):
    with closing(sqlite3.connect(reader[3])) as c, c:
        c.executescript("DROP TABLE settings; CREATE TABLE settings(models TEXT); INSERT INTO settings VALUES('fixture');")
    result=reader[0].inspect()
    assert row(result,"Context length")["status"]=="could_not_read"
    assert row(result,"Model location")["value"]=="fixture"

def test_cloud_log_has_historical_label(reader):
    (reader[1]/"server.log").write_text('time=fixture msg="Ollama cloud disabled: true"\n')
    r=row(reader[0].inspect(),"Cloud")
    assert "Disabled" in r["value"] and "startup" in r["value"]

def test_saved_cloud_without_log(reader):
    directory=reader[2]/".ollama";directory.mkdir()
    (directory/"server.json").write_text('{"disable_ollama_cloud":true}')
    r=row(reader[0].inspect(),"Cloud")
    assert r["status"]=="read" and "Disabled" in r["value"]
    assert "verified" in r["value"] or "confirmed" in r["value"]

def test_version_and_updater_keys_present(reader):
    result=reader[0].inspect()
    assert "version" in result and "updater" in result
    assert result["version"]["status"] in ("read","unrecognized_response","unknown")
    assert result["updater"]["status"] in ("in_confirmed_affected_range","outside_confirmed_affected_range","unknown")

def test_updater_finding_inside_affected_range(reader):
    finding=reader[0].updater_finding({"version":"0.15.0"},"Enabled")
    assert finding["status"]=="in_confirmed_affected_range"
    assert "0.12.10" in finding["message"]

def test_updater_finding_outside_range_never_claims_patched(reader):
    finding=reader[0].updater_finding({"version":"0.40.16"},"Enabled")
    assert finding["status"]=="outside_confirmed_affected_range"
    assert "unverified" in finding["message"]
    assert "Do not assume" in finding["message"]

def test_updater_finding_unknown_version(reader):
    finding=reader[0].updater_finding({"version":None},"Enabled")
    assert finding["status"]=="unknown"

def test_database_bytes_unchanged_and_no_chat_select(reader,monkeypatch):
    db=reader[3];before=db.read_bytes();queries=[]
    original=sqlite3.connect
    def connect(*args,**kwargs):
        c=original(*args,**kwargs);c.set_trace_callback(queries.append);return c
    monkeypatch.setattr(sqlite3,"connect",connect)
    reader[0].inspect()
    assert db.read_bytes()==before
    assert not any("messages" in q.lower() for q in queries)
    assert not any(q.lstrip().upper().startswith(("INSERT ","UPDATE ","DELETE ","VACUUM","DROP ")) for q in queries)
