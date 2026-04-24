# Claude Code Briefing — FortiGate Checkmk Plugin

You are working on the `fortigate_firmware` Checkmk 2.4 plugin. Read this entire file before doing anything.

## Read these first

1. `docs/ARCHITECTURE.md` — full audit of the existing plugin: file inventory, data flow, conventions, established patterns, known issues.
2. `docs/FIXUP_PLAN.md` — the chunked work plan with locked-in decisions, validation gates, rollback strategy.

## Working environment

- **Repo location:** `~/projects/checkmk-fortigate/` in WSL Ubuntu 24.04.
- **Checkmk version:** 2.4.0 (Check API v2, Rulesets API v1, Server-Side Calls API v1, Graphing API v1).
- **Test site:** Docker container `cmk-test` (image `checkmk/check-mk-raw:2.4.0-latest`), site name `cmk`, GUI at `http://localhost:8080/cmk/`.
- **Test host:** `fw-test` configured in the Checkmk GUI, pointed at a real FortiGate.
- **Plugin source tree:** `local/lib/python3/cmk_addons/plugins/fortigate_firmware/`.

## Dev loop — use this exact sequence

After ANY edit to plugin files:

```bash
./scripts/deploy-test.sh         # auto-detects what to restart, runs cmk-validate-plugins
```

If validation fails, fix the issue before doing anything else. Do not try to deploy around a validation failure.

After deploy, verify behavior:

```bash
# Raw agent output (ground truth — what the special agent actually returned)
docker exec -u cmk cmk-test bash -lc 'cmk -d fw-test'

# Dry-run check (what state each check would compute, without committing)
docker exec -u cmk cmk-test bash -lc 'cmk -nv fw-test'

# The actual command line Checkmk built for the special agent
docker exec -u cmk cmk-test bash -lc 'cmk -D fw-test'
```

For GUI changes (rulesets/, server_side_calls/, graphing/), the deploy script will trigger `omd restart`; hard-refresh the browser (Ctrl+F5) to pick up rule changes.

## Hard rules (don't violate without explicit instruction)

1. **Result() is kwargs-only.** `Result(state=State.OK, summary="...")`. Positional args raise `TypeError`.
2. **Agent sections always use `:sep(0)`** for JSON payloads. `<<<section_name:sep(0)>>>`.
3. **The agent never raises out** — it always emits a section, with a structured error payload if needed (see `_error_payload` in `libexec/agent_fortigate`).
4. **Service display name ≠ check plugin internal name** is OK, but document it. Internal name describes the data; service name describes the user-facing thing.
5. **Family directory name is misleading** (`fortigate_firmware` covers system + firmware + license). Chunk 6 of the fixup plan renames it to `fortigate`. Don't anticipate the rename in earlier chunks.
6. **Clear `__pycache__` and `*.pyc`** after every edit. The deploy script handles this; if you bypass it, do this manually.
7. **Don't break the three baseline services.** System OK, Firmware Updates WARN/OK, Services License OK/WARN/CRIT. After any change, re-verify all three.
8. **Each chunk is one commit.** Don't bundle chunks together. Don't half-implement a chunk and move on.

## Conventions to follow

(Full list in `docs/ARCHITECTURE.md` §5. Summary:)

- Imports — `from cmk.agent_based.v2 import ...`, `from cmk.rulesets.v1 import ...`, `from cmk.server_side_calls.v1 import ...`, `from cmk.graphing.v1 import ...`.
- Plugin variables at module bottom — `agent_section_<n> = AgentSection(...)`, `check_plugin_<n> = CheckPlugin(...)`.
- Error state mapping — connection/timeout → UNKNOWN, auth on primary check → CRIT, auth on secondary check → WARN.
- Configuration delivery — Pattern A (special-agent payload injection) for host-wide config; Pattern B (separate check-parameters ruleset) for per-service thresholds.

## What to do when stuck

- **Validator complains about API misuse:** check the file against `docs/ARCHITECTURE.md` §5; the imports/usage there are confirmed working.
- **GUI shows old behavior after edit:** stale Apache. Run `./scripts/deploy-test.sh --full` to force `omd restart`.
- **GUI shows "Unimplemented check" or vanished services:** `__pycache__` not cleared, or check plugin internal name changed. Run deploy script (it clears caches).
- **Special agent returns nothing:** check `cmk -D fw-test` to see the exact command line. Then SSH into the container and run that command manually with the credentials.
- **Anything else:** explain the symptom and ask before guessing.

## What to ask before doing

- Any change beyond the current chunk's scope.
- Any new dependency.
- Any change to the dev-loop script.
- Any change to git history (rebases, force-pushes).
- Any production-side action (we test in Docker; production is hands-off until Chunk 6 sign-off).
