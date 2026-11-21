"""Read-only Windows Ollama desktop settings evidence. No online account checks."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

LABELS = ["Sign in", "Cloud", "Auto-download", "Expose Ollama to the network", "Model location", "Context length"]

_AFFECTED_RANGE = ((0, 12, 10), (0, 17, 5))  # CVE-2026-42248/42249 confirmed-affected Ollama versions

def _version_tuple(text):
    try:
        return tuple(int(p) for p in text.split("-")[0].split("+")[0].split(".")[:3])
    except (ValueError, AttributeError):
        return None

def detect_version():
    """Best-effort Ollama version. Reports the source; never guesses."""
    result = {"version": None, "source": None, "status": "unknown"}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request("http://127.0.0.1:11434/api/version"), timeout=3) as response:
            raw = response.read(8192)
        value = json.loads(raw).get("version")
        if isinstance(value, str) and _version_tuple(value):
            result.update(version=value, source="local Ollama API /api/version", status="read")
            return result
        result["status"] = "unrecognized_response"
    except Exception:
        pass
    exe = shutil.which("ollama")
    if exe:
        try:
            proc = subprocess.run([exe, "--version"], capture_output=True, timeout=5)
            text = (proc.stdout or proc.stderr or b"").decode("utf-8", "replace")
            match = re.search(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)", text)
            if proc.returncode == 0 and match:
                result.update(version=match.group(1), source="ollama --version (" + exe + ")", status="read")
        except (OSError, subprocess.SubprocessError):
            pass
    return result

def updater_finding(version_info, auto_update_value):
    version = version_info.get("version")
    parsed = _version_tuple(version) if version else None
    base = {"auto_update": auto_update_value, "cves": ["CVE-2026-42248", "CVE-2026-42249"],
            "reference": "https://nvd.nist.gov/vuln/detail/CVE-2026-42248"}
    if parsed is None:
        return dict(base, status="unknown",
                    message="Ollama version could not be determined; updater exposure is unassessed.")
    low, high = _AFFECTED_RANGE
    if low <= parsed <= high:
        return dict(base, status="in_confirmed_affected_range",
                    message="Ollama " + version + " is inside the confirmed-affected range (0.12.10-0.17.5) for unsigned Windows auto-updates. Verify the vendor fix before relying on auto-update.")
    return dict(base, status="outside_confirmed_affected_range",
                message="Ollama " + version + " is outside the confirmed-affected range (0.12.10-0.17.5); vendor fix status is unverified. Do not assume this version is patched.")

def inspect():
    rows = {label: dict(label=label, value=None, status="could_not_read", reason="Not read.", source=None) for label in LABELS}
    def put(label, value, source, **extra):
        rows[label].update(value=value, status="read", reason=None, source=source, **extra)
    def fail(label, reason, source=None):
        rows[label].update(reason=reason, source=source)
    directory = Path(os.environ["LOCALAPPDATA"]) / "Ollama" if os.environ.get("LOCALAPPDATA") else None
    db = directory / "db.sqlite" if directory else None
    connection = None
    try:
        if db is None or not db.is_file() or db.is_symlink():
            raise OSError("Ollama db.sqlite not found or is a symbolic link.")
        connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        def table(name, wanted):
            columns = {r[1] for r in connection.execute('PRAGMA table_info("' + name + '")')}
            present = [c for c in wanted if c in columns]
            if not present:
                raise ValueError("Expected columns are absent in " + name)
            order = ' ORDER BY "id"' if "id" in columns else ''
            row = connection.execute('SELECT ' + ','.join('"'+c+'"' for c in present) + ' FROM "'+name+'"' + order + ' LIMIT 1').fetchone()
            return None if row is None else dict(zip(present, row))
        try:
            user = table("users", ["name", "plan"])
            evidence = "Ollama app database · users table · local cache only; no online verification"
            name = user.get("name") if user else None
            if isinstance(name, str) and name.strip():
                plan = user.get("plan")
                text = "Cached account: " + name.strip()
                if isinstance(plan, str) and plan.strip():
                    text += " · plan: " + plan.strip()
                put("Sign in", text + " (current sign-in status not verified)", evidence,
                    account_cache="present", authentication_status="not_verified")
            else:
                state = "empty" if user is None else "no_account_name"
                put("Sign in", "No cached account; sign-in status not verified (not proof of sign-out)", evidence,
                    account_cache=state, authentication_status="not_verified")
        except (sqlite3.Error, ValueError) as exc:
            fail("Sign in", "Could not read account cache: " + str(exc))
        labels = LABELS[2:]
        try:
            settings = table("settings", ["auto_update_enabled", "expose", "models", "context_length"])
            if settings is None:
                raise ValueError("No saved settings row.")
            for label, column in [("Auto-download", "auto_update_enabled"), ("Expose Ollama to the network", "expose")]:
                evidence = "Ollama app database · settings table · " + column
                value = settings.get(column)
                if column in settings and type(value) is int and value in (0, 1):
                    put(label, "Enabled" if value else "Disabled", evidence)
                else:
                    fail(label, "Missing or unexpected Boolean value; not guessed.", evidence)
            evidence = "Ollama app database · settings table · models"
            if "models" not in settings:
                fail("Model location", "Column is absent.", evidence)
            elif isinstance(settings["models"], str) and settings["models"].strip():
                put("Model location", settings["models"], evidence)
            elif settings["models"] is None or settings["models"] == "":
                put("Model location", "Default location (no custom path saved)", evidence)
            else:
                fail("Model location", "Unexpected value type.", evidence)
            evidence = "Ollama app database · settings table · context_length"
            if "context_length" not in settings:
                fail("Context length", "Column is absent.", evidence)
            else:
                value = settings["context_length"]
                rows["Context length"].update(raw_value=value, raw_type="null" if value is None else type(value).__name__)
                if type(value) is int and value > 0:
                    put("Context length", f"{value:,} tokens (saved override; raw = {value})", evidence,
                        interpretation="saved_override", effective_value_verified=False)
                elif type(value) is int and value == 0:
                    put("Context length", "Raw saved value: 0 · no positive desktop override; computed default not read", evidence + " · upstream desktop uses computed default when saved value is zero; installed-version behavior not verified",
                        interpretation="zero_no_positive_override", effective_value_verified=False)
                elif value is None:
                    put("Context length", "Raw saved value: NULL · numeric meaning not established", evidence,
                        interpretation="null_unresolved", effective_value_verified=False)
                else:
                    fail("Context length", "Unexpected raw saved value: " + repr(value) + "; not interpreted.", evidence)
        except (sqlite3.Error, ValueError) as exc:
            for label in labels:
                fail(label, "Could not read settings: " + str(exc))
    except (OSError, sqlite3.Error) as exc:
        for label in ["Sign in"] + LABELS[2:]:
            fail(label, "Could not read local database: " + str(exc))
    finally:
        if connection is not None:
            connection.close()
    json_value = None
    notes = []
    config = Path.home() / ".ollama" / "server.json"
    try:
        if config.is_symlink():
            raise ValueError("symbolic link not followed")
        with config.open("rb") as stream:
            raw = stream.read(262145)
        if len(raw) > 262144:
            raise ValueError("file too large")
        data = json.loads(raw)
        candidate = data.get("disable_ollama_cloud") if isinstance(data, dict) else None
        if type(candidate) is bool:
            json_value = candidate
            notes.append("server.json disable_ollama_cloud = " + str(candidate).lower())
        else:
            notes.append("server.json has no Boolean disable_ollama_cloud")
    except (OSError, ValueError) as exc:
        notes.append("server.json unavailable: " + type(exc).__name__)
    log_value = None
    if directory:
        for name in ["server.log"] + [f"server-{i}.log" for i in range(1, 6)]:
            path = directory / name
            try:
                if path.is_symlink():
                    continue
                with path.open("rb") as stream:
                    stream.seek(0, 2)
                    stream.seek(max(0, stream.tell() - 2 * 1024 * 1024))
                    text = stream.read(2 * 1024 * 1024).decode("utf-8", "replace")
                for line in reversed(text.splitlines()):
                    match = re.search(r"Ollama cloud disabled:\s*(true|false)", line, re.I)
                    if match:
                        log_value = match[1].lower() == "true"
                        stamp = re.search(r"time=(\S+)", line)
                        notes.insert(0, name + " startup line (" + (stamp[1] if stamp else "time unknown") + ")")
                        break
                if log_value is not None:
                    break
            except OSError:
                pass
    env = os.environ.get("OLLAMA_NO_CLOUD")
    if env is not None:
        notes.append("helper environment OLLAMA_NO_CLOUD = " + env + " (not proof of server environment)")
    source = " · ".join(notes)
    if log_value is not None:
        put("Cloud", ("Disabled" if log_value else "Enabled") + " (as of last recorded Ollama startup)", source)
    elif json_value is not None:
        put("Cloud", ("Disabled" if json_value else "Enabled") + " (saved in server.json; running state not verified)", source)
    else:
        fail("Cloud", "No explicit saved cloud setting or startup record found.", source)
    count = sum(r["status"] == "read" for r in rows.values())
    version_info = detect_version()
    updater = updater_finding(version_info, rows["Auto-download"].get("value"))
    return dict(connected=count > 0, settings=[rows[label] for label in LABELS], discovery=[],
                version=version_info, updater=updater,
                error=None if count else "None of the six settings could be read.",
                note="Read-only local evidence, not live settings or account verification. Installed-version context-default semantics are not verified.")
