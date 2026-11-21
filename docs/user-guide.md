# OllamaPrivacyController — User Guide

A local privacy dashboard for Ollama on Windows. It shows you where your AI
conversations live, lets you apply a reversible privacy preset, and removes
interaction history — always with preview and confirmation.

**Requirements:** Windows 10/11, Python 3.10+, Ollama installed.
**Verified on:** Ollama 0.40.16.

---

## Getting started

1. Open a terminal in the project folder.
2. Run:

   ```powershell
   py server_with_settings.py
   ```

3. Open `http://127.0.0.1:8765` in your browser.
4. Hard-refresh once (**Ctrl+F5**) if the page looks stale.

> **Important:** always start `server_with_settings.py` — not `server.py`.
> The plain `server.py` serves the page but the cleanup, settings, and test
> features won't work.

The dashboard listens only on `127.0.0.1:8765` for access from this computer.

---

## The interface

**Left sidebar** — seven pages:

| Page | What it shows |
|---|---|
| **Dashboard** | Connection status, version, overview of all 4 areas, cleanup controls |
| **CLI history** | Inspection detail for `~/.ollama/history` |
| **Desktop database** | Inspection detail for `db.sqlite` chats/messages/attachments |
| **Logs** | Inspection detail for `server*.log`, `app*.log`, and other log files |
| **Saved models** | Inventory of model manifests/blobs and message-layer candidates |
| **Configuration** | Current settings evidence + the privacy preset controls |
| **Tests** | Buttons to run the Python and JavaScript test suites |

**Top bar** — the **Theme** dropdown (Copper / Light / Slate / Dark) and a
helper status badge. Theme choice is saved in your browser.

**Big button:** **"Check my Ollama setup"** (top of every page) runs the
read-only inspection and populates all four area tabs at once.

---

## Page-by-page

### Dashboard

- **Ollama connection** — whether the local Ollama API answered, and its version
- **Inspection overview** — one-line summary per area (e.g., "2 log candidates · 2 fully read")
- **Manual cleanup** (collapsed) — the deletion workflow, covered below
- **Model cleanup (disabled)** — shows what *would* be cleaned for saved
  sessions; intentionally off in v0.1
- **Session activity** — a log of your recent scans

### Area tabs (CLI history / Desktop database / Logs / Saved models)

Each shows:

- A plain-language summary line
- A **table of every location inspected** — path, context (which account),
  status (`found` / `empty` / `not_found` / `access_denied` / etc.), with a
  **"Technical details"** expander per row (sizes, timestamps, schema info)
- A **"Limitations & caveats"** expander — read these; they state exactly what
  was *not* verified

Honest-labeling examples you may see:

- "Line storage was inspected, not certified as individual prompt records"
- "Zero active rows does not establish absence of recoverable content"
- "Cached account: … (current sign-in status not verified)"

### Configuration

Two cards:

**1. Current Ollama Settings** — click **"Refresh Ollama settings"** to read
local evidence. Shows 6 settings (Sign in, Cloud, Auto-download, Expose to
network, Model location, Context length) plus **Ollama version** and
**Windows auto-update risk** (CVE-2026-42248/42249 check). Read-only — changes
nothing.

**2. Ollama configuration** — the preset controls:

| Button | What it does |
|---|---|
| **Read settings** | Loads your current saved `OLLAMA_*` values (user + machine scope) |
| **Stage privacy preset** | Fills in the 5 recommended values as a *proposal* — changes nothing yet |
| **Review changes** | Shows the exact before → after for every variable |
| **Review restore** | Previews restoration of a previously applied change set; changes nothing until confirmed |

After **Review changes**, a panel shows each variable's current vs. proposed
value. Tick **"I approve these exact saved-setting changes"** → **Apply
approved changes**. The app verifies the write by reading the registry back,
and keeps a backup so a later restore can undo it.

The preset sets:

| Variable | Value | Meaning |
|---|---|---|
| `OLLAMA_DEBUG` | `0` | Normal logging (not "logging off") |
| `OLLAMA_DEBUG_LOG_REQUESTS` | `false` | No request dumps |
| `OLLAMA_NOHISTORY` | `true` | Disables new CLI readline-history recording; does not disable desktop chat storage |
| `OLLAMA_NO_CLOUD` | `true` | Cloud features off |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Loopback only — no LAN access |

> **After applying:** quit Ollama (system tray → Quit) and relaunch it. The
> app can't restart Ollama for you, and can't verify the running process
> picked up the new values. Only *new* sessions are affected — nothing
> historical is deleted by the preset.

### Tests

- **Run Python tests** — the backend suite (~80 tests, all synthetic data)
- **Run JS tests** — the frontend suite (~8 tests, simulated DOM)

Results appear inline with expandable failure details. Only one suite runs
at a time; a second click while running returns a busy message.

---

## Task walkthroughs

### "I want to see what AI data Ollama has on my machine"

1. Click **Check my Ollama setup**
2. Read the Dashboard overview lines
3. Click each area tab for the full location table
4. Expand **Limitations & caveats** on any area that matters to you

Nothing is modified — inspection is strictly read-only.

### "I want to reduce future CLI history recording and disable cloud features"

1. **Configuration** tab → **Current Ollama Settings** → **Refresh Ollama
   settings** (see what you're starting from)
2. **Read settings** → **Stage privacy preset** → **Review changes**
3. Check the before/after table — confirm it matches what you expect
4. Tick the consent box → **Apply approved changes**
5. Quit Ollama from the tray and relaunch it
6. To undo later: **Review restore** → consent → apply

### "I want to delete my Ollama interaction history"

**Recommended:** quit Ollama first (system tray → Quit). Deleting while it
runs can fail on locked files — the app will tell you per-file.

1. **Dashboard** → expand **Manual cleanup**
2. Click **Plan cleanup** — the app shows the cleanup targets, including
   file sizes and database row counts where available. Nothing is deleted
   yet.
3. Review the targets. If a warning says "Ollama should be stopped," stop it
   and click **Plan cleanup** again (plans expire after 5 minutes and are
   invalidated if targets change).
4. For each area you want cleaned: tick **"I approve these exact deletions"**
   → click **Delete selected targets**
5. The results panel shows per-target outcomes — **deleted / failed /
   skipped / access denied** — plus a verification re-scan

**Heads-up:** log and database deletion removes *entire files/rows*. There
is no "delete only today" mode in v0.1. For the desktop database, deleted
rows may linger in SQLite free pages until you run `VACUUM` manually — the
results panel says so.

### "I want to remove saved-session models (`/save`)"

Saved-session/model-artifact cleanup is disabled in v0.1. To remove a saved
model, use `ollama rm <name>`. The **Saved models** tab provides inspection
only; this release does not offer manual manifest/blob deletion instructions.

---

## Troubleshooting

| Symptom | Possible cause / next step |
|---|---|
| Cleanup buttons do nothing | The page may be served by `server.py` — restart with `server_with_settings.py` |
| "Cleanup plan expired or invalid" (409) | Plans last 5 minutes and die if targets change. Plan again and execute promptly |
| "Cleanup targets changed" (409) | A file appeared/disappeared/changed since your plan — possibly Ollama writing logs. Stop Ollama, re-plan |
| `access_denied` on log/db targets | Ollama may be running and holding the files. Quit it and retry |
| "Could not read" on settings rows | The Ollama desktop app may not be installed, or files are locked. Other rows still populate |
| Page looks unstyled | Ctrl+F5; the Bulma CSS is served locally, no CDN needed |
| `file://` warning in console | The page was opened directly — use `http://127.0.0.1:8765` instead |

---

## v0.1 boundaries

- **Does not delete model weights or your downloaded models**
- **Does not cover** Docker/WSL installs, other user accounts, third-party
  chat UIs, or remote/cloud records in this release (see `docs/coverage.md`)
- **No forensic-erasure claims** — SQLite free pages may retain deleted rows
- **Windows 10/11 only**
- **Does not stop or restart Ollama,** or verify that its running process
  adopted the saved environment changes

## Privacy behavior

- The controller does not upload inspected interaction data and includes no
  telemetry
- Frontend assets are served locally — no CDN, no external requests