# OllamaPrivacyController

A local-first privacy dashboard for [Ollama](https://ollama.com) on Windows. It answers three questions about your local installation:

1. **What interaction data exists** on this machine — and where?
2. **Where is it configured**, and what do those settings actually do?
3. **How do I remove it** — safely, with preview and confirmation?

**Status: v0.1 — Windows 10/11 only.** Verified against Ollama 0.40.16 (November 2026).

## What it does

### Inspection (read-only)

Scans the local Ollama data stores defined in `docs/security-areas.txt` and reports findings with sources, sizes, and explicit limitations — it labels what it *inspected* versus what it *certified*:

- **CLI prompt history** (`%USERPROFILE%\.ollama\history`)
- **Desktop app database** (`%LOCALAPPDATA%\Ollama\db.sqlite` + WAL/SHM/journal companions) — opened read-only
- **Log files** (`server.log`, rotated `server-#.log`, explicit redirections)
- **Saved sessions / custom models** (`models/manifests`, `models/blobs`) — inventory and message-layer candidates

### Desktop settings reader

Reads six settings from local evidence (desktop database, `server.json`, log startup lines) and reports each with its source and honest uncertainty — e.g., a cached account name is *not* a live sign-in check. It also reports:

- **Ollama version** (from the local `/api/version` endpoint or `ollama --version`, with the source named)
- **Windows auto-update risk** — correlates the version against the confirmed-affected range for CVE-2026-42248/CVE-2026-42249 and the auto-update setting. Wording is deliberately non-committal: versions outside the confirmed range are reported as *"vendor fix status unverified,"* never as patched.

### Privacy preset (reversible)

Applies a reviewed set of `OLLAMA_*` environment variables to the Windows current-user registry:

| Variable | Preset value | Effect |
|---|---|---|
| `OLLAMA_DEBUG` | `0` | Normal INFO logging (not a logging-off switch) |
| `OLLAMA_DEBUG_LOG_REQUESTS` | `false` | Disables future request dumps; does not delete existing ones |
| `OLLAMA_NOHISTORY` | `true` | Disables new CLI readline history; does not disable desktop chat storage |
| `OLLAMA_NO_CLOUD` | `true` | Disables cloud features; local integrations may lose cloud functionality |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Loopback only; LAN clients lose access after restart |

Workflow: read current values → stage changes → review exact before/after → confirm → apply. Changes are verified by registry read-back, backed up to `%LOCALAPPDATA%\OllamaPrivacyController\configuration-backup.json`, and reversible via Restore. **Restart Ollama manually** — the tool never restarts it and cannot verify the running process picked up new values.

### Confirmed cleanup (Security Areas 1–3)

- **Preview** exact targets (files, rows, sizes) before anything is deleted
- **Server-issued, expiring plan token** (5 minutes) — execution rejects expired, unknown, or stale plans whose targets changed since review
- Per-target results: **deleted / failed / skipped / access denied**, plus post-cleanup re-inspection
- Honest residuals: SQLite free pages may retain deleted content until `VACUUM` is run manually

| Area | Cleanup behavior |
|---|---|
| 1. CLI history | Deletes entire per-account history files (no per-entry dates exist) |
| 2. Desktop database | Deletes rows from `chats`, `messages`, `attachments`, `tool_calls`; WAL checkpoint after commit |
| 3. Logs | Deletes entire log files; warns that Ollama should be stopped first |

## What it does NOT do

- **Does not delete model weights or tokenizers** — and Area 4 (saved-session/model-artifact cleanup) ships **disabled** pending shared-blob safety review
- **Does not claim forensic erasure** — deleted SQLite rows can persist in free pages; OS-level remnants (swap, backups, snapshots) are out of scope
- **Does not cover Areas 5–10** — temp prompt files, OS/infra artifacts, Docker/WSL/VMs, third-party frontends, remote records (see `docs/coverage.md`)
- **Windows 10/11 only** — macOS/Linux code paths exist but are untested
- **Does not control the Windows auto-updater** — it reports version/update risk as a finding only
- **Does not verify runtime state** — saved settings are not proof Ollama is running with them

## What the preset leaves alone

Model downloads from the ollama.com registry, the Windows auto-updater, non-`OLLAMA_*` settings in `server.json`/`db.sqlite`, and anything outside the current-user environment.

## Requirements

- Windows 10/11, Python 3.10+ (standard library only — no pip packages for the app)
- Ollama installed (inspection degrades gracefully if absent)
- For tests: `pytest` (see `requirements-test.txt`) and Node.js 20+ with `npm install` (jsdom, dev-only)

## Run

```powershell
py server_with_settings.py
```

Open `http://127.0.0.1:8765`. The helper binds to loopback only and rejects non-local origins.

## Tests

```powershell
py -m pytest          # Python suite (synthetic data only)
npm test              # JS/jsdom suite
```

The dashboard's **Tests** page runs the same suites in-app. Runs are serialized, time-limited (2 min), use fixed command lists with no user input, disable pytest plugin autoload, and execute with your account's permissions — only run tests you trust.

## Project layout

```
server.py               Base server: scan/config routes, CSRF/origin guards, static allowlist
server_with_settings.py Entry point: adds settings reader, cleanup endpoints, test runner
configuration.py        Reversible OLLAMA_* env preset engine (plan/apply/restore)
desktop_settings.py     Read-only settings evidence + version/updater findings
model_cleanup.py        Saved-model cleanup — plan only; execute disabled
checks/                 Inspection + cleanup checkers (base, cli_history, desktop_database, logs, saved_models)
script/                 Frontend modules (app, configuration, desktop_settings, cleanup, model_cleanup, tests, theme)
index.html, css/        UI (Bulma + themes.css)
tests/, tests-js/       Test suites
```

## Documentation

- `docs/coverage.md` — Security Areas coverage matrix and cleanup status
- `docs/security.md` — threat model, deletion semantics, limitations
- `docs/security-areas.txt` — the coverage source-of-truth document
- `docs/user-guide.md` — end-user walkthroughs and troubleshooting
- `docs/release-plan-v0.1.md` — release plan and wording rules

## License

MIT — see `LICENSE`.
