# Claude Code Briefing — FortiGate Checkmk Plugin

Read this entire file at the start of every session before doing anything else.

---

# Part 1 — Working Principles

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- Plan claims about untouched code or declarative-API behavior are hypotheses to verify, not facts to trust. Validators catch structural issues, not behavioral assumptions.
- If something is unclear, stop. Name what's confusing. Ask.

### In this project that means:

- If `docs/FIXUP_PLAN.md` is ambiguous about a chunk's scope, ask before interpreting. Example: Chunk 1 says "standardize `parse_fortigate_license`" — if you're unsure whether that means just the `chain.from_iterable` pattern or also error-handling consistency, ask.
- If a file appears to have an existing bug that's not listed in the chunk scope, mention it — don't silently fix it (that's a #3 violation) and don't pretend you didn't see it.
- If the FortiGate API response shape differs from what the existing code expects, stop and report. Don't invent a new parser that handles both shapes without confirmation.
- If an imported name (e.g., a FormSpec class) doesn't exist in the site's Checkmk version, check whether there's an intentional defensive fallback in the existing code before "fixing" the import.
- When a chunk's scope text or audit asserts behavior of code or a declarative API the chunk does not touch, treat the assertion as a probe-target before relying on it. Past surfacings: Chunk 2 Lesson #1 (License discovery had the same gating bug Chunk 2 was fixing in System, contrary to "NOT needed for firmware/license discovery"), Chunk 4 Lesson #1 (refinement), Chunk 5 Lesson #1 (bare-`Metric()` auto-graph behavior invalidated a declarative-API plan claim that `cmk-validate-plugins` could not catch).

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### In this project that means:

- The existing plugin uses defensive `try/except ImportError` blocks for optional FormSpec classes (e.g., `SingleChoice` fallback to `BooleanChoice`). These are intentional. Do NOT "clean them up."
- Don't add type hints to functions that don't have them. Match existing style.
- Don't introduce `dataclasses`, `typing.Protocol`, `pydantic`, or other typing machinery. Plain dicts are the house style.
- Don't wrap simple values in helper classes. The plugin passes dicts around; keep it that way.
- Don't add logging beyond what's present. The special agent emits JSON sections; that's its logging.
- When in doubt, the smaller diff is correct.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### In this project that means:

- Each chunk in `docs/FIXUP_PLAN.md` has an explicit scope. If the chunk says "extract error classifier" — touch only the error-classifier code and its two call sites. Do not reformat `check_fortigate_system` beyond that.
- Do not rename variables, reorder function arguments, or reflow multi-line expressions unless the chunk explicitly requires it.
- Do not "modernize" `%` string formatting to f-strings or vice versa. Match what's already in the file.
- Do not add or remove blank lines around unrelated code.
- If you spot an issue outside chunk scope, add it to `docs/FIXUP_PLAN.md` under a "Deferred" section — do not fix it inline.
- If a single file needs changes for two different chunks, that's a signal to re-read the plan, not to bundle them.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### In this project that means:

- Every chunk in `docs/FIXUP_PLAN.md` has a written "validation gate." Use it as your success criterion, not your intuition.
- Primary verification tools in order of preference: `cmk-validate-plugins` (syntax and API usage), `cmk -d fw-test` (raw agent output), `cmk -nv fw-test` (computed check state), GUI service list.
- Before starting a chunk, state: (1) the files you expect to touch, (2) the files you expect NOT to touch, (3) how you'll know it worked.
- If the validation gate fails, iterate on the fix — don't move on to the next chunk.
- "Looks right in the diff" is not a validation. Run the deploy script.

---

# Part 2 — Project Context

## What this project is

The `fortigate` Checkmk 2.4 plugin, in its fix-up phase. Goal: improve the production plugin, then extract a reusable template repo for future Checkmk special-agent plugins.

## Read these next

1. `docs/ARCHITECTURE.md` — full audit: file inventory, data flow, conventions, known issues.
2. `docs/FIXUP_PLAN.md` — the chunked work plan with locked-in decisions, validation gates, rollback strategy.

## Working environment

- **Repo location:** `~/projects/checkmk-fortigate/` in WSL Ubuntu 24.04.
- **Checkmk version:** 2.4.0 (Check API v2, Rulesets API v1, Server-Side Calls API v1, Graphing API v1).
- **Test site:** Docker container `cmk-test` (image `checkmk/check-mk-raw:2.4.0-latest`), site name `cmk`, GUI at `http://localhost:8080/cmk/`.
- **Test host:** `fw-test`, pointed at a real FortiGate. Baseline verified: System OK, Firmware Updates WARN, Services License CRIT (expired license on the FortiGate).
- **Plugin source tree:** `local/lib/python3/cmk_addons/plugins/fortigate/`.
- **Remote:** `https://github.com/alexsabin/checkmk-fortigate` (private).

## Dev loop — use this exact sequence

After ANY edit to plugin files:

```bash
./scripts/deploy-test.sh         # auto-detects what to restart, runs cmk-validate-plugins
```

If validation fails, fix the issue before doing anything else. Do not try to deploy around a validation failure.

After deploy, verify behavior:

```bash
docker exec -u cmk cmk-test bash -lc 'cmk -d fw-test'   # raw agent output (ground truth)
docker exec -u cmk cmk-test bash -lc 'cmk -nv fw-test'  # dry-run check state
docker exec -u cmk cmk-test bash -lc 'cmk -D fw-test'   # resolved special-agent command line
```

For GUI changes (rulesets/, server_side_calls/, graphing/), the deploy script triggers `omd restart`; hard-refresh the browser (Ctrl+F5) to pick up rule changes.

---

# Part 3 — Hard Rules

Do not violate these without explicit instruction.

1. **`Result()` is kwargs-only.** `Result(state=State.OK, summary="...")`. Positional args raise `TypeError`.
2. **Agent sections always use `:sep(0)`** for JSON payloads. `<<<section_name:sep(0)>>>`.
3. **The special agent never raises out** — it always emits a section, with a structured error payload if needed (see `_error_payload` in `libexec/agent_fortigate`).
4. **Service display name ≠ check plugin internal name** is OK, but document it. Internal name describes the data; service name describes the user-facing thing.
5. **Family directory name matches the vendor, not the first-shipped feature.** A family covers all data types one vendor's special agent emits — current example: `fortigate/` holds system + firmware + license.
6. **Clear `__pycache__` and `*.pyc`** after every edit. The deploy script handles this; if you bypass it, do so manually.
7. **Don't break the three baseline services.** System OK, Firmware Updates WARN/OK, Services License OK/WARN/CRIT. After any change, re-verify all three.
8. **Each chunk is one commit.** Don't bundle chunks. Don't half-implement a chunk and move on.

---

# Part 4 — Per-Chunk Checklist

Before committing any chunk, walk through this list. If you cannot check a box, stop and fix.

- [ ] **Scope:** every changed line traces to this chunk's explicit scope in `docs/FIXUP_PLAN.md` (principle #3).
- [ ] **Boundary:** no files changed outside this chunk's scope.
- [ ] **No speculation:** no abstractions, type hints, or error handling added that the chunk didn't require (principle #2).
- [ ] **Deploy:** `./scripts/deploy-test.sh` completes with zero validation errors.
- [ ] **Behavior:** the three baseline services still appear in `fw-test`'s service list.
- [ ] **Validation gate:** the chunk's specific validation gate in `docs/FIXUP_PLAN.md` passes.
  - For path-changing edits (rename, package-name change, family-directory change, server-side-call relocation), the gate must include a precompiled-path probe (`cmk -II <host>` + `cmk -O` then a live-monitoring check, or GUI service list inspection) in addition to `cmk -nv`. For non-path-changing edits, `cmk -nv` alone is sufficient.
- [ ] **Diff review:** `git diff --stat` + `git diff` — diff is small enough to review in under 5 minutes; nothing surprising.
- [ ] **Forward-pointer scan:** scan each new Lesson and Deferred entry's prose for forward-pointers (references to specific other Deferred entries, future chunks by number, or specific files/sections to be edited later); for each forward-pointer found, edit the target now in the same commit, never as a thing-to-remember.
- [ ] **Commit message:** one line says what changed, one paragraph says why (references the chunk).
- [ ] **Deferred items:** anything noticed but not fixed is recorded in `docs/FIXUP_PLAN.md` under "Deferred."
- [ ] **Close-out commit ritual:** every chunk-body commit is followed by a separate close-out commit (Lessons additions plus any Deferred-entry annotations or resolutions). Its body must include:
  - **Per-Chunk Checklist enumeration** — a block headed `Per-Chunk Checklist (12 items, explicit enumeration):` followed by items 1–12 in prose, each naming what was actually done for it in this chunk. Item 7 is item 6's Validation-gate-composition sub-bullet enumerated as its own line; items 8–12 then map to Diff review, Forward-pointer scan, Commit message, Deferred items, and Close-out commit ritual respectively. Item 12 (this item) prescribes the close-out commit's own shape; the self-reference is mechanical, not recursive. If Part 4 grows or shrinks, update the literal `12` in the same edit.
  - **Forward-pointer scan output** — item 9 of the enumeration above must report the scan's output explicitly: positive enumeration of pointers found and propagated in the same commit, or the empty-scan-as-information shape: `Forward-pointer scan — empty. New Lessons reference [back-pointers list]. No specific forward-pointers per the Part 4 criterion.` Empty scan is recorded as information, not success.

---

# Part 5 — What to Ask Before Doing

- Any change beyond the current chunk's scope.
- Any new dependency (pip package, system tool).
- Any change to the dev-loop script.
- Any change to git history (rebases, force-pushes, tag moves).
- Any production-side action (production is hands-off until Chunk 7 sign-off).
- Any change to `CLAUDE.md`, `docs/ARCHITECTURE.md`, or `docs/FIXUP_PLAN.md`.

---

# Part 6 — What to Do When Stuck

- **Validator complains about API misuse:** check the file against `docs/ARCHITECTURE.md` §5; the imports/usage there are confirmed working.
- **GUI shows old behavior after edit:** stale Apache. Run `./scripts/deploy-test.sh --full` to force `omd restart`.
- **GUI shows "Unimplemented check" or vanished services:** `__pycache__` not cleared, or check plugin internal name changed. Run deploy script (it clears caches).
- **Special agent returns nothing:** check `cmk -D fw-test` to see the exact command line. Then run that command manually inside the container with the same environment.
- **Something feels off in the plan itself:** stop. Raise it. Don't improvise around the plan.
- **Validator fails with duplicate-plugin-definition errors after a family rename:** the old family directory is still in the container alongside the new one. Delete it by hand once — `docker exec cmk-test rm -rf /omd/sites/cmk/local/lib/python3/cmk_addons/plugins/<old-family>` — then re-deploy.
- **A service goes UNKN with `No module named '<old.import.path>'` after a structural change:** the per-host precompiled bundle has the old import path baked in. Re-inventory and recompile per host: `docker exec -u cmk cmk-test cmk -II <host>`, then `cmk -O`, then Activate Changes.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
