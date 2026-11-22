# Security Areas Coverage

Source of truth: `docs/security-areas.txt`. This matrix states what v0.1 actually does — nothing more.

**Platform scope:** Windows 10/11 is verified. macOS is an untested beta with synthetic tests only. Linux is unsupported. On macOS beta, configuration uses the user launchd session plus generated Login Items agents; coverage of every Ollama install method is not guaranteed.

## Areas 1–4 (local Ollama data stores)

| Area | Name | Inspection | Privacy setting | Deletion | Verification | Status |
|------|------|------------|-----------------|----------|--------------|--------|
| 1 | CLI history | ✓ | ✓ `OLLAMA_NOHISTORY` | ✓ whole-file, plan-bound | ✓ re-inspect | Supported |
| 2 | Desktop database | ✓ read-only | ✗ | ✓ row DELETE + WAL checkpoint | ✓ re-inspect | Supported (not forensic) |
| 3 | Logs | ✓ | partial (`OLLAMA_DEBUG`, `OLLAMA_DEBUG_LOG_REQUESTS`) | ✓ whole-file | ✓ re-inspect | Supported |
| 4 | Saved models | ✓ inventory | ✗ | ✗ **disabled** | n/a | Plan preview only |

## Areas 5–10 (out of scope for v0.1)

| Area | Name | Why deferred |
|------|------|--------------|
| 5 | Temporary prompt files | Editor-specific, conditional; small enough for v0.2 |
| 6 | Configuration/identity | Metadata, not interaction content; partially covered by settings reader |
| 7 | Docker/WSL/VMs | Requires per-environment adapters |
| 8 | Frontends/extensions | Third-party applications, not Ollama |
| 9 | OS infrastructure copies | Forensic scope far beyond a local utility |
| 10 | Remote records | Outside local-tool scope by definition |

## Cleanup safety model

1. `GET /api/cleanup/plan` returns per-checker plans **plus a server-issued token** (5-minute expiry, bound to the session CSRF token).
2. `POST /api/cleanup/execute` requires `{checker_id, plan_token, confirmed: true}`. It rejects expired/unknown tokens, re-plans, and refuses if the target set changed since review.
3. Checkers skip symlinks, re-validate `is_file()` at execute time, and report per-target status.
4. `saved_models` is excluded from general cleanup; `/api/model-cleanup/execute` always returns 503.

## Known residuals (honest limits)

- SQLite `DELETE` does not erase free pages — deleted chat content may remain recoverable until `VACUUM`. VACUUM is not performed automatically.
- WAL checkpoint is attempted after commit; residual WAL frames depend on the live database state.
- Log files may be recreated by a running Ollama; deletion is not a disable-logging control.
- CLI history deletion is whole-file per account; there are no per-entry dates.
- Only the current user's account and configured candidate paths are inspected — other users, containers, and remote servers are not discovered.
- "Zero rows" or "file gone" after verification means the *active* records are gone, not that bytes are unrecoverable.
