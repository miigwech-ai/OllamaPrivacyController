# Security & Threat Model

## What this tool is

A loopback-only local utility. It reads Ollama data stores, applies reversible
current-user environment settings, and performs confirmed deletion of
interaction records for Security Areas 1–3.

## Trust boundaries

- **Bind:** `127.0.0.1:8765` only. No LAN exposure.
- **Origin checks:** every request requires a local `Host` header, same-origin
  `Origin` (or none), and rejects `Sec-Fetch-Site: cross-site`.
- **CSRF:** all POSTs require `X-OPC-CSRF` matching a per-process token.
- **Body limits:** JSON bodies capped (1 KB tests, 16 KB config/cleanup);
  chunked transfer encoding rejected; 10 s socket timeout.
- **Static files:** allowlist only; paths resolved and confined to the project root.
- **Test runner:** fixed command lists (`pytest` on three named files, `node --test`
  on `tests-js/*.test.cjs`); no user-supplied commands; plugin autoload disabled;
  120 s timeout with process-tree kill. It executes project code with your
  account's privileges — only run tests you trust.

## Destructive operations

Cleanup uses plan-binding: the server issues a 5-minute token at plan time;
execute requires the token plus `confirmed: true`, re-plans, and refuses if
targets changed. Configuration changes use the same pattern plus platform
read-back verification (registry on Windows, `launchctl getenv` on macOS beta)
and automatic rollback on write failure. macOS login persistence uses generated
LaunchAgents and is untested.

Checkers never follow symlinks, never copy interaction content into logs or
responses, and report per-target outcomes instead of claiming success.

## What is NOT guaranteed

- **Forensic erasure.** `DELETE` leaves SQLite free pages; OS-level remnants
  (pagefile, swap, backups, snapshots, volume shadow copies) are untouched.
- **Runtime enforcement.** Saved `OLLAMA_*` values are not proof the running
  Ollama process uses them; existing processes keep their launch environment.
- **Complete coverage.** Areas 5–10 (editor temp files, OS artifacts,
  Docker/WSL, third-party UIs, remote records) are out of scope.
- **Updater safety.** CVE-2026-42248/CVE-2026-42249 affect Ollama's Windows
  auto-updater; this tool reports version/update status as a finding but
  cannot fix or disable the updater.
- **Concurrent-writer safety.** Cleanup warns when Ollama should be stopped
  but does not detect or stop running processes. Stop Ollama before cleanup.
