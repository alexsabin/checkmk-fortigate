# Fix-up Plan for the FortiGate Plugin

This document is the source of truth for the fix-up phase. Read top to bottom before starting any chunk. Each chunk is one git commit and is independently revertible.

## Context

- Project: bring the existing `fortigate_firmware` Checkmk 2.4 plugin onto a clean, repeatable framework before extracting a reusable plugin template.
- Baseline: tagged `v1.1.0-baseline-verified` — confirmed working against a real FortiGate (System OK, Firmware Updates WARN with branch comparison, Services License CRIT with day-threshold logic).
- Read `docs/ARCHITECTURE.md` first for the full audit, conventions, and rationale.

## Working environment

- Code lives in WSL Ubuntu 24.04 at `~/projects/checkmk-fortigate/`.
- Test site: Docker container `cmk-test` running `checkmk/check-mk-raw:2.4.0-latest`, GUI at `http://localhost:8080/cmk/` (login `cmkadmin` / `testpass123`), site name `cmk`.
- Test host: `fw-test` configured with the special-agent rule, monitoring a real FortiGate.
- Deploy loop: `./scripts/deploy-test.sh` (smart restart based on what changed).
- Per-chunk validation: GUI service states unchanged or changing exactly as the chunk intends, plus `cmk -d fw-test` and `cmk -nv fw-test` outputs.

## Locked-in decisions

1. Family rename `fortigate_firmware` → `fortigate` (Chunk 6, last).
2. Webfilter thresholds become a check-parameters ruleset (Pattern B example for the future template).
3. Graphing stub gets replaced with proper Graphing API v1 definitions for all metrics.
4. API key continues to be passed via CLI argument (current pattern is fine for our threat model).
5. Order: fix the production plugin first, then extract the template from it.

## Conventions to preserve (from audit §5)

- One special agent → N agent sections → N check plugins.
- Agent emits `<<<section:sep(0)>>>` + one JSON object per line. Always.
- Agent never raises — always emits a section, with an `error` payload if needed.
- Error classification: connection/timeout → UNKNOWN, auth on primary check → CRIT, auth on secondary check → WARN.
- `Result()` is always kwargs-only.
- Configuration delivered to checks via Pattern A (special-agent rule → CLI flags → agent injects into payload → check reads from `section["config"]`) OR Pattern B (separate check-parameters ruleset → params via check function signature). Use B when thresholds need per-service overrides.
- Naming: family = vendor, agent section = `<vendor>_<datatype>`, check plugin internal name = `<vendor>_<what>`, service display name = human Title Case phrase, special agent / ruleset key = `<vendor>`.

## Chunks

### Chunk 1 — internal cleanup (zero behavior change)

- Delete all `.bak.*` files.
- Delete `graphing/fortigate_firmware.py` stub (Chunk 4 replaces it).
- Extract the duplicated error-classification logic (the keyword-mapping in `check_fortigate_system` and `check_fortigate_firmware`) into `agent_based/_errors.py`. Both check functions import from it.
- Standardize `parse_fortigate_license` to use the same `itertools.chain.from_iterable` pattern as the other two parsers.
- Add `checkman/fortigate_webfilter_expires` (use the existing two as templates).
- Bump `.mkp-builder.ini`: `version.min_required = 2.4.0p1`, `version.packaged = <next>`.
- Add `*.bak.*` to `.gitignore`.

Validation gate: deploy → all three services discover, all three show identical summary/details to baseline. `diff <(cmk -nv fw-test [old]) <(cmk -nv fw-test [new])` should be empty.

### Chunk 2 — discovery robustness

- In `discover_fortigate_system`, yield `Service()` whenever any section is received, not only when `status == "success"`.
- Rationale: today, a host with a broken API key never gets the service discovered, so the CRIT that would tell you the key is broken is never visible.
- Same change is NOT needed for firmware/license discovery — they already discover unconditionally.

Validation gate: with working API key, service still appears as OK. Temporarily break the API key in the rule (e.g. append "x"), redeploy on a new test host, rediscover — service should appear with CRIT, not vanish. Restore key.

### Chunk 3 — Pattern B for webfilter thresholds

- Add `rulesets/webfilter_expires.py` defining `CheckParameters` with `Integer` fields for `warn_days` (default 30) and `crit_days` (default 15).
- Update `agent_based/fortigate_webfilter_expires.py`:
  - Check function signature: `def check_fortigate_webfilter_expires(params: Mapping[str, Any], section: ...) -> CheckResult`.
  - Add `check_default_parameters={"warn_days": 30, "crit_days": 15}` and `check_ruleset_name="fortigate_webfilter_expires"` to `CheckPlugin(...)`.
  - Replace hardcoded 30/15 with `params["warn_days"]` / `params["crit_days"]`.
- Add a checkman update if needed.

Validation gate: with no rule, behaves identically. Create a rule overriding to WARN 60 / CRIT 30 → service threshold logic changes without a redeploy (Apply changes only).

### Chunk 4 — Graphing API v1

- Create `graphing/fortigate.py` (or `graphing/fortigate_firmware.py` if Chunk 6 hasn't run yet — the file just needs to be inside `graphing/`).
- `Metric(...)` definitions for: `updates_available` (count), `security_updates` (count), `builds_behind_latest` (count), `builds_behind_recommended` (count), `major_versions_behind` (count), `minor_versions_behind` (count), `version_numeric` (count), `build_number` (count), `days_until_webfilter_expiry` (time, days).
- One or two `Graph(...)` groupings: e.g. firmware-gap graph combining `builds_behind_*`; license expiry as its own graph.
- No perfometers initially.

Validation gate: open each service in the GUI, metrics display with correct units in graph views. No log warnings about unknown metrics.

### Chunk 5 — documentation & repo polish

- Rewrite `README.md` for the three services + the new ruleset, plus the gotchas (`:sep(0)`, kwargs-Result, pycache-clearing, family-name rename if Chunk 6 done).
- Add `CONTRIBUTING.md` with the dev loop (becomes template fodder later).
- Confirm `.gitignore` excludes `*.bak.*`, `__pycache__/`, `*.pyc`, `build/`.

Validation gate: README matches what `cmk -D fw-test` and the GUI actually show. No drift.

### Chunk 6 — family rename + release

- Rename directory `fortigate_firmware/` → `fortigate/`.
- Rename `graphing/fortigate_firmware.py` → `graphing/fortigate.py` if not already.
- Update `.mkp-builder.ini`: `name = fortigate`, bump version to `2.0.0`.
- Update README/scripts/anywhere paths are referenced.
- Update `scripts/deploy-test.sh`: change `FAMILY` default to `fortigate`.
- Build a fresh MKP locally (or via CI tag).
- Test-site swap: `mkp disable fortigate_firmware && mkp remove fortigate_firmware`, install new MKP, confirm all three services keep their state (check plugin internal names didn't change, so service identity is preserved).

Validation gate: after MKP swap, services continue reporting with same history. Tag `v2.0.0`, push, let CI build the MKP.

Production migration (separate session, after test-site swap is proven): `mkp disable && mkp remove` old, install new, `cmk -R`, activate changes. Spot-check the three services on the production FortiGate.

## Rollback strategy

- Each chunk is one git commit. `git revert <sha>` + redeploy reverses any chunk.
- Test site is throwaway — `docker rm -f cmk-test` and re-run the bring-up if it gets stuck.
- Production migration in Chunk 6: keep the old MKP file (download it before removing) so rollback is `mkp remove fortigate && mkp install fortigate_firmware-1.1.0.mkp` + rediscover.

## Things to remember (from production runbook + audit)

- Always clear `__pycache__` and `*.pyc` after edits — stale bytecode causes silent ghost behavior.
- After ruleset / server_side_calls changes, full `omd restart` is required (the deploy script handles this automatically).
- Service rename creates vanished-old + undecided-new in the GUI — accept the new ones, remove the vanished ones, activate.
- `cmk -d <host>` shows raw agent output; `cmk -nv <host>` shows what each check would compute; `cmk -D <host>` shows the resolved special-agent command line.
- Special agent `libexec/agent_*` MUST be executable (mode 755). Exit 126 = permission denied.

## Deferred

### System check is_unknown precedence bug

In `agent_based/fortigate.py`, `check_fortigate_system` computes `is_unknown` as:

  `is_unknown = err_type in (...) or any(...) or any(...) if detail else False`

Python precedence makes this parse as `(whole_expression) if detail else False`, so `is_unknown` is False whenever `detail` is empty/None, regardless of `err_type`. The firmware check at lines 140-144 uses correct parentheses and is the reference implementation.

Currently latent because `_error_payload` always populates `detail`, but would surface if any future agent change produces error payloads without `detail`.

Fix: adopt the firmware check's parenthesized form in the system check. Validation: construct a payload with missing `detail` and `err_type="connection"`, confirm service goes UNKNOWN not CRIT. Schedule as its own chunk after Chunk 6 so the diff is reviewable in isolation.

## Lessons from Chunk 1

Captured at the close of Chunk 1 application. Useful context when planning future chunks.

1. **Latent `is_unknown` precedence bug in `check_fortigate_system`.** Surfaced during the
   `_errors.py` extraction. See the "Deferred" section above for the full description and
   proposed fix; scheduled as its own chunk after Chunk 6.

2. **Edit-tool trailing-whitespace stripping.** The Claude Code Edit tool silently
   normalizes trailing whitespace on lines it touches, both when matching `old_string` and
   when writing `new_string`. For files with intentional trailing whitespace (e.g., the
   original import block in `agent_based/fortigate.py`), use `sed -i` or `python3 -c` for
   byte-level edits.

3. **`deploy-test.sh` missing-directory bug.** The original `find` pipeline aborted under
   `set -euo pipefail` when any of `rulesets/`, `server_side_calls/`, or `graphing/` was
   absent — surfaced in Chunk 1 when stub deletion + `git stash`/`pop` left `graphing/`
   missing (git doesn't track empty dirs). Fixed in commit `300f79d`. The script now
   enumerates existing GUI subdirectories before invoking `find`.

4. **Per-chunk tagging convention adopted.** Each chunk's successful application is
   recorded with an annotated tag named `chunk<N>-applied` (e.g., `chunk1-applied`).
   `v`-prefixed tags (`v1.1.0-baseline-verified`, future `v2.0.0`) are reserved for
   release / baseline milestones.
