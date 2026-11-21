# OllamaPrivacyController — v0.1 Release Plan

**Goal:** Ship an honest, Windows-only v0.1 covering inspection, settings evidence,
reversible env configuration, and confirmed cleanup for Security Areas 1–3.
Areas 4–10 are documented as out of scope.

**Definition of done:** tests pass, every README claim verified against code,
cleanup is plan-bound and stale-safe, repo is clean, tagged `v0.1.0`.

---

## Phase A — Safety fixes (do first)

### A1. Fix `plan()` read-write SQLite connection
- **File:** `checks/desktop_database.py`
- **Problem:** `plan()` opened SQLite read-write just to `COUNT(*)` rows. That could create `-wal`/`-shm` companions or contend with running Ollama — in a *preview* step.
- **Fix:** Use the same read-only URI pattern as `inspect()` (`mode=ro` + `PRAGMA query_only=ON` + progress-handler deadline).
- **Regression test:** temp-dir DB; after `plan()`, assert DB bytes unchanged and no `-wal`/`-shm`/`-journal` files exist.

### A2. Plan-binding for cleanup endpoints
- **Files:** `server_with_settings.py` (`/api/cleanup/plan`, `/api/cleanup/execute`)
- **Pattern to copy:** `configuration.py` — token, 5-min expiry, session binding, stale-state re-check at apply.
- **Design:** `/api/cleanup/plan` stores plans server-side keyed by token
  (checker_id → plan dict + expiry). `/api/cleanup/execute` accepts
  `{plan_token, confirmed}` only — never client-supplied targets. At execute:
  reject expired/unknown token, reject session mismatch, re-run `plan()` and
  compare target sets; reject if changed.
- **Tests:** expired token rejected; changed file list since preview rejected;
  confirmed=false rejected; saved_models still routed to its own endpoint.

### A3. Ollama version detection + updater finding
- **File:** `desktop_settings.py`
- **Sources (in priority order, name which was used):**
  1. Local Ollama API `/api/version`
  2. `ollama --version` subprocess (timeout-guarded)
- **Finding logic:** report version + source; compare against confirmed-affected
  range **0.12.10–0.17.5** (CVE-2026-42248/42249); combine with existing
  `auto_update_enabled` row ("Auto-download").
- **Wording (fixed):** "Version X is outside the confirmed-affected range
  (0.12.10–0.17.5); vendor fix status unverified." Never imply 0.40.x is patched.
  If version can't be determined: "unknown" — never guess.
- **Link:** https://nvd.nist.gov/vuln/detail/CVE-2026-42248

### A4. Honest verification reporting
- Per-target statuses: deleted / failed / skipped / access_denied / unverified.
- Results copy states: deleted rows may persist in SQLite free pages;
  VACUUM is manual opt-in (not implemented in v0.1).

---

## Phase B — Tests

- Run `py -m pytest` and `npm test`; fix all failures.
- New tests (all synthetic temp data, no real Ollama paths):
  - `plan()` creates no companion files (A1)
  - cleanup plan token expiry / reuse rejection (A2)
  - cleanup rejects when targets changed since preview (A2)
  - schema-mismatch refusal for desktop DB cleanup (missing tables → fail plan)
  - version-detection fallback → "unknown" (A3)
- If test files are added, update hardcoded list in `server_with_settings.py`.
- Keep the in-app test runner; document its guards in README
  (loopback-only, Host/Origin/CSRF checks, fixed suite names, no command
  interpolation, 120s timeout, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`).

---

## Phase C — Repo hygiene

- `.gitignore`: `__pycache__/`, `*.pyc`, `node_modules/`, `.pytest_cache/`,
  `backups/`, `*.tmp`
- Delete/archive: `debug_db_execute*.py`, `OllamaPrivacyController-tests.zip`,
  the `.docx`, `next-phase.md`, handoff docs → `docs/history/` or delete
- `backups/` — verify unreferenced, then remove
- Add `LICENSE` (MIT)
- Optional: `pyproject.toml` (pip-installable); NOT required for v0.1

---

## Phase D — Documentation (write LAST, verify every claim)

- **`README.md`** (consolidates README.txt + 6 other *-README.txt + COVERAGE.md
  + VALIDATION.txt):
  - Lead: three questions — what interaction data exists, where is it
    configured, how do I remove it
  - "Verified on" line: Windows 10/11, Ollama 0.40.16, test date
  - **Two separate tables:**
    - Reader: 6 desktop settings (Sign in, Cloud, Auto-download, Expose,
      Model location, Context length) — each with evidence source +
      "verified on 0.40.16" column
    - Preset: 5 env vars (OLLAMA_DEBUG, OLLAMA_DEBUG_LOG_REQUESTS,
      OLLAMA_NOHISTORY, OLLAMA_NO_CLOUD, OLLAMA_HOST) — each with impact text
      matching `configuration.py` `impact` fields verbatim
  - "What it does NOT do" near top: no model-weight deletion, no forensic
    erasure, Areas 4–10 out of scope, Windows-only, updater not configurable
  - "What the preset leaves alone": ollama.com registry downloads, Windows
    auto-updater, non-`OLLAMA_*` settings in `server.json`/`db.sqlite`
  - `OLLAMA_DEBUG=0` described as "normal logging", never "logging off"
  - Architecture section; test instructions; limitations
- **`docs/coverage.md`:** area matrix updated to match reality
  (Areas 1–3 cleanup ✓, Area 4 disabled, 5–10 deferred with rationale)
- **`docs/security.md`:** threat model, plan-binding design, what's NOT
  guaranteed (free pages, WAL remnants, running-process limits)

---

## Phase E — Release

- Manual smoke test on real (disposable) Ollama install — synthetic tests
  don't cover the real paths
- `git tag v0.1.0`; GitHub release with notes; link from portfolio

---

## v0.1 → v1.0 roadmap (public)

| Feature | Notes |
|---|---|
| Area 4 saved-session/model cleanup | Needs shared-blob reference analysis + plan binding |
| VACUUM / secure-delete option | Explicit opt-in, careful testing |
| macOS + Linux support | Code paths exist, untested |
| Area 5 temp prompt files | Small, well-defined |
| Scheduled cleanup | UX around safe-deletion timing |
| Ollama version compatibility matrix | Confidence for 1.0 |
| Optional PyInstaller `.exe` | Removes Python dependency |

## Fixed wording rules (do not violate)

- Never claim "privacy-first guarantee" — describe what the preset changes
- Never claim "forensic erasure" or "complete deletion"
- Never imply Ollama 0.40.x is patched against CVE-2026-42248
- Never claim cross-platform support
- Reader shows 6 settings; preset writes 5 — present as two tables
- Cleanup "server-issued, expiring plan" claim is ONLY true after A2 ships
