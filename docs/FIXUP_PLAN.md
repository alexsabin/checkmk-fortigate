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

1. Family rename `fortigate_firmware` → `fortigate` (Chunk 7, last).
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
- Delete `graphing/fortigate_firmware.py` stub (Chunk 5 replaces it).
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

### Chunk 4 — license discovery robustness (one-line fix, promoted from Deferred)

- In `discover_fortigate_webfilter_expires`, change the gate from `isinstance(section.get("web_filtering"), dict)` to `if section:` — same fix Chunk 2 applied to `discover_fortigate_system`, and the same shape `discover_fortigate_firmware` already had.
- Rationale: when the agent emits a structured error payload (no `web_filtering` key), the License service was never discovered, so a broken API key produced a vanished service instead of a visible error state. The check function already handles missing-`web_filtering` (yields UNKNOWN), so gating discovery on the key being a dict was strictly too tight.
- Promoted ahead of Graphing because the bug is the same class as Chunk 2's, was already documented under Deferred, and the Chunk 2 negative-test infrastructure was warm.

Validation gate: same negative-test pattern as Chunk 2 — drop License autocheck, mangle inline token in `etc/check_mk/conf.d/wato/rules.mk`, rediscover, confirm Services License appears in both `cmk -nv` and `cmk -D` (state classification UNKNOWN/CRIT is informational; the gate is presence vs. vanished). Restore token byte-perfect, re-verify the three baseline services unchanged (Hard Rule #7).

### Chunk 5 — Graphing API v1

- Create `graphing/fortigate.py` (or `graphing/fortigate_firmware.py` if Chunk 7 hasn't run yet — the file just needs to be inside `graphing/`).
- `Metric(...)` definitions for: `updates_available` (count), `security_updates` (count), `builds_behind_latest` (count), `builds_behind_recommended` (count), `major_versions_behind` (count), `minor_versions_behind` (count), `version_numeric` (count), `build_number` (count), `days_until_webfilter_expiry` (time, days).
- One or two `Graph(...)` groupings: e.g. firmware-gap graph combining `builds_behind_*`; license expiry as its own graph.
- No perfometers initially.

Validation gate: open each service in the GUI, metrics display with correct units in graph views. No log warnings about unknown metrics.

### Chunk 6 — documentation & repo polish

- Rewrite `README.md` for the three services + the new ruleset, plus the gotchas (`:sep(0)`, kwargs-Result, pycache-clearing, family-name rename if Chunk 7 done).
- Add `CONTRIBUTING.md` with the dev loop (becomes template fodder later).
- Confirm `.gitignore` excludes `*.bak.*`, `__pycache__/`, `*.pyc`, `build/`.

Validation gate: README matches what `cmk -D fw-test` and the GUI actually show. No drift.

### Chunk 7 — family rename + release

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
- Production migration in Chunk 7: keep the old MKP file (download it before removing) so rollback is `mkp remove fortigate && mkp install fortigate_firmware-1.1.0.mkp` + rediscover.

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

Fix: adopt the firmware check's parenthesized form in the system check. Validation: construct a payload with missing `detail` and `err_type="connection"`, confirm service goes UNKNOWN not CRIT. Schedule as its own chunk after Chunk 7 so the diff is reviewable in isolation.

## Lessons from Chunk 1

Captured at the close of Chunk 1 application. Useful context when planning future chunks.

1. **Latent `is_unknown` precedence bug in `check_fortigate_system`.** Surfaced during the
   `_errors.py` extraction. See the "Deferred" section above for the full description and
   proposed fix; scheduled as its own chunk after Chunk 7.

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

## Lessons from Chunk 2

Captured at the close of Chunk 2 application.

1. **Plan assertions about adjacent code are hypotheses, not facts.** The Chunk 2
   scope note said "Same change is NOT needed for firmware/license discovery —
   they already discover unconditionally." Negative testing proved this correct
   for firmware but wrong for license (`web_filtering`-dict gate, same class of
   bug Chunk 2 was fixing in System). Recorded under Deferred. For future chunks,
   treat plan statements about untouched code as claims to verify, not facts to
   trust — particularly when the chunk's own change exercises the same code path
   in a sibling check.

2. **Negative tests with mangled credentials can trip the FortiGate WAF.** Rapid
   `cmk -d` / `cmk -II` cycles with a broken bearer token produced HTTP 429 (Too
   Many Requests) responses for ~60-90 seconds, masking the expected 401 auth
   failures. For future credential-failure validation, build in a
   wait-for-rate-limit-clear step (poll `cmk -d <host>` until the response stops
   returning 429) before asserting final service state.

## Lessons from Chunk 3

Captured at the close of Chunk 3 application.

1. **Pattern B verification: don't rely on state-transition gates when an
   absolute-state branch can short-circuit threshold logic.** The intuitive way
   to validate a check-parameters ruleset is to override the defaults and watch
   the service state change (e.g., set WARN low enough to flip OK → WARN). That
   gate produces a false pass whenever the check has an absolute-state branch
   upstream of any threshold comparison. In `check_fortigate_webfilter_expires`,
   an expired license matches `if seconds_left <= 0:` and yields CRIT before
   either `params["crit_days"]` or `params["warn_days"]` is consulted, so *no*
   threshold override (not WARN=60/CRIT=30, not even WARN=99999/CRIT=99998)
   produces a state transition on the test host. The state stays CRIT
   regardless of params, which reads as "override worked" but proves nothing
   about the rule reaching the check function. The correct probe in this
   situation is `cmk -D <host>`, which dumps each service's resolved
   check-parameters dict — with no rule it shows
   `{'warn_days': 30, 'crit_days': 15}`; with an override rule active it shows
   the new dict. That proves rule-spec ↔ `check_ruleset_name` linkage and
   rule-merge behavior end-to-end without depending on the check's internal
   control flow. Apply this approach in any future Pattern B chunk (and bake it
   into the eventual template) whenever the check has an absolute-bad-state
   branch ahead of its threshold ladder — which is most expiry, connectivity,
   and auth checks.

## Lessons from Chunk 4

Captured at the close of Chunk 4 application.

1. **Refinements, not new lessons.** Chunk 4 validated Chunks 2 and 3 lessons in
   combination: Chunk 2's WAF rate-limit-clear poll was prepared but unneeded
   on this run (the FortiGate returned 401 on the first probe, confirming that
   the WAF behavior is non-deterministic and the poll is right to keep but
   won't always fire); Chunk 3's `cmk -D` probe served as the second
   independent assertion of License-service-presence under broken credentials,
   paired with `cmk -nv`. The two-probe shape — service list via `cmk -D`,
   computed state via `cmk -nv` — is the established negative-test pattern for
   future discovery-robustness chunks (and a different application of `cmk -D`
   than Chunk 3's Pattern B verification, but the same underlying lesson:
   `cmk -D` is the truth probe whenever `cmk -nv` alone is ambiguous).

## Lessons from Chunk 5

Captured at the close of Chunk 5 application.

1. **Audit-as-hypothesis discipline applies to declarative chunks too — Chunk 2
   Lesson #1 reapplied to a declarative surface.** Chunk 5 was scoped on the
   implicit audit assumption that declaring a `Metric()` without a containing
   `Graph()` would render as "declare-only, no graph in the service view."
   Runtime invalidated that: Checkmk's Graphing API v1 auto-renders any
   unclaimed metric as a single-metric graph, with no opt-out. Confirmed by
   inspection — `cmk.graphing.v1.metrics.Metric` has exactly four fields
   (`name`, `title`, `unit`, `color`); the full v1 surface (1280 LOC across 7
   files) has no `hidden=`, no `auto_graph=False`, no exclusion registry. The
   lesson is not "the API is missing a feature" — it's that plan-claims about
   declarative-API *behavior* are hypotheses, not facts, and
   `cmk-validate-plugins` cannot catch behavioral assumptions, only structural
   ones. Accepted outcomes: (a) the System auto-graphs (`version_numeric`,
   `build_number`) are documented visual drift since the perfdata exists either
   way, (b) the per-chunk validation gate for declarative chunks is updated to
   enumerate *all* graphs that appear on each service detail page, not just
   the explicitly-declared ones. Generalization for future declarative chunks
   (graphing, perfometers, ruleset forms): drop a probe into the GUI to
   observe actual rendered behavior before declaring scope finalized.

2. **Mixed-unit graphs hard-fail at render time, not at validate time.** A
   `Graph(simple_lines=[a, b])` where `a` and `b` have different `Unit(...)`
   definitions — even when both render visually as bare integers (e.g., our
   `Unit(DecimalNotation(""), StrictPrecision(0))` paired with upstream's
   `Unit(DecimalNotation(""), StrictPrecision(2))`) — causes Checkmk to
   refuse rendering: "Cannot create graph with metrics of different units."
   `cmk-validate-plugins` does not catch this; only the GUI does. When
   grouping metrics from multiple owners (some declared in our file, some
   declared upstream), verify the upstream `Unit` matches ours before
   grouping — or accept that the cross-owner metric will auto-graph
   standalone. Side-observation, not investigated: standalone auto-graph
   rendering for upstream-owned metrics (the `security_updates` case after
   Fix 1) appears inconsistent — the perfdata reaches Checkmk and shows in
   the Metrics text list ("Pending security updates: 4"), but the standalone
   auto-graph wasn't visibly present in post-fix screenshots. No Chunk 5
   lever remains, since touching either the upstream definition or the
   check's perfdata name is out of scope.

3. **Metric names are a global Checkmk namespace, not per-plugin.** First
   Chunk 5 deploy raised
   `plug-in 'security_updates' already defined at cmk.plugins.collection.graphing.updates`.
   Generic names (`security_updates`, `temperature`, `cpu_load`,
   `updates_available` — anything that could plausibly mean the same thing
   across vendors) are most likely already owned upstream. Pre-flight before
   declaring `Metric()`s in any future graphing file:
   `grep -rln 'name="<metric>"' /omd/sites/<site>/lib/python3/cmk/plugins/*/graphing/`
   for each name. Resolution when a collision exists on *existing* perfdata:
   drop our duplicate and accept upstream's title/unit/color — renaming the
   perfdata in the check function would break Hard Rule #7 (RRD discontinuity
   for any consumer already plotting the metric). For *new* perfdata in
   future plugins, prefer context-prefixed names (e.g.,
   `fortigate_security_updates` rather than `security_updates`) to avoid the
   same forced compromise.

4. **ARCHITECTURE.md §5 needs a Graphing API v1 conventions subsection.** The
   pattern established in `graphing/fortigate_firmware.py` (canonical imports,
   `UNIT_*` constants, `metric_<bare_name>` variable convention matching the
   `name=` field, four-graph grouping driven by scale-spread analysis,
   declare-don't-group for identity metrics with the auto-graph caveat from
   Lesson #1, accept-upstream for collisions per Lesson #3) is the source
   material for Chunk 6 to formalize.

5. **Chunk 7 rename surface expanded by Chunk 5.** Three of the four graph
   `name=` strings declared in `graphing/fortigate_firmware.py` carry the
   family-prefix `fortigate_firmware_*`
   (`fortigate_firmware_updates_available`, `fortigate_firmware_builds_behind`,
   `fortigate_firmware_versions_behind`). When Chunk 7 renames the family
   directory to `fortigate`, these strings become part of the rename sweep.
   Flagged for Chunk 7's scope only — Hard Rule #5 (no anticipating the
   rename in earlier chunks) applies.
