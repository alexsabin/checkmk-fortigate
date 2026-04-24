# FortiGate Plugin — Architecture Audit

**Source audited:** `fortigate_firmware` plugin family, live copy from `/omd/sites/fvemon/local/lib/python3/cmk_addons/plugins/fortigate_firmware/` + repo root files.
**Checkmk target version:** 2.4.0 (Check API v2 / Rulesets API v1 / Server-Side Calls API v1).
**Purpose of this document:** capture the "house style" already established, so the future template repo and all subsequent plugins follow the same conventions.

---

## 1. Executive summary

The existing plugin is **well-structured and correctly uses the Checkmk 2.4 APIs**. It's a solid starting point — no rewrites needed, just some clean-up and formalization. Three services are exposed from a single special agent:

| Service (displayed) | Check plugin (internal) | Agent section | API endpoint |
|---|---|---|---|
| FortiGate System | `fortigate_system` | `fortigate_system` | `/api/v2/monitor/system/status` |
| FortiGate Firmware Updates | `fortigate_firmware` | `fortigate_firmware` | `/api/v2/monitor/system/firmware` |
| Services License | `fortigate_webfilter_expires` | `fortigate_license` | `/api/v2/monitor/license/status?vdom=root` |

The plugin is a clean example of the **"one special agent, N sections, N check plugins"** pattern that the template repo should formalize.

---

## 2. File inventory (live)

```
fortigate_firmware/
├── agent_based/
│   ├── fortigate.py                       (system + firmware checks, ~500 lines)
│   └── fortigate_webfilter_expires.py     (license check, ~100 lines)
├── checkman/
│   ├── fortigate_firmware                 (man page: firmware)
│   └── fortigate_system                   (man page: system)
│                                          (NO man page for webfilter_expires — gap)
├── graphing/
│   └── fortigate_firmware.py              (empty stub — see §7)
├── libexec/
│   └── agent_fortigate                    (special agent, Python, ~240 lines)
├── rulesets/
│   └── special_agent.py                   (GUI rule, ~108 lines)
└── server_side_calls/
    └── special_agent.py                   (CLI builder, ~50 lines)
```

**Repo-root packaging files:**
```
checkmk-fortios-fw/
├── .github/workflows/build.yml   (CI: tag push → MKP → GH release via oposs/mkp-builder@v2)
├── .gitignore                     (excludes build/, __pycache__, *.pyc, venv)
├── .mkp-builder.ini              (MKP metadata; see §7 for version pinning issue)
├── LICENSE                        (GPL-3.0)
└── README.md
```

---

## 3. Data flow

```
GUI rule "FortiGate Firmware"  (rulesets/special_agent.py)
       │  params dict: {api_key, port?, timeout?, critical_on_branch_change?, ok_if_unmatured_branch?}
       ▼
server_side_calls/special_agent.py :: _agent_arguments(params, host_config)
       │  builds CLI args, unwraps password via .unsafe()
       ▼
libexec/agent_fortigate  (Python special agent, runs on Checkmk server)
       │  HTTPS to {hostname}:{port}/api/v2 with Bearer token
       │
       ├─► GET /monitor/system/status
       │       → print "<<<fortigate_system:sep(0)>>>" + JSON line
       │
       ├─► GET /monitor/system/firmware
       │       → normalize payload shape (7.6 vs older FortiOS)
       │       → inject config flags into payload.config
       │       → print "<<<fortigate_firmware:sep(0)>>>" + JSON line
       │
       └─► GET /monitor/license/status?vdom=root
               → extract results.web_filtering, reshape
               → print "<<<fortigate_license:sep(0)>>>" + JSON line
       ▼
agent_based/fortigate.py
       │  AgentSection(fortigate_system) → parse → discover → check → "FortiGate System"
       │  AgentSection(fortigate_firmware) → parse → discover → check → "FortiGate Firmware Updates"
       │
agent_based/fortigate_webfilter_expires.py
       │  AgentSection(fortigate_license) → parse → discover → check → "Services License"
       ▼
Checkmk monitoring
```

---

## 4. API / integration details

- **Protocol:** HTTPS REST, base URL `https://{hostname}:{port}/api/v2`
- **Auth:** `Authorization: Bearer <api_key>` header
- **TLS:** `verify=False`, `urllib3.disable_warnings(InsecureRequestWarning)` (FortiGates typically use self-signed certs)
- **Timeout:** configurable, default 30 seconds
- **Port:** configurable, default 443
- **Hostname resolution:** `host_config.primary_ip_config.address or host_config.name` (falls back to name if no IP)
- **Password handling:** `cmk.rulesets.v1.form_specs.Password` with `migrate=migrate_to_password` → stored in Checkmk password store, unwrapped server-side via `params["api_key"].unsafe()`

---

## 5. Established conventions ("house style")

These are the patterns already present in the code. They become the rules the template repo enforces.

### 5.1 Agent section emission
- **Always `:sep(0)`** for JSON payloads (null byte separator).
- **One JSON object per line**, no trailing content.
- **On success:** emit payload as-is (or minimally reshaped).
- **On error:** emit a structured error payload with fields `status: "error"`, `error: <category>`, `message: <short>`, `endpoint: <path>`, `detail: <full exception str>`.
- **Never** raise out of the agent — always emit a section even on error, so the check can report status.

### 5.2 Error classification (in agent)
`_error_payload(exc, endpoint)` helper categorizes into:
- `timeout` — `ConnectTimeout` / `ReadTimeout` / "timed out"
- `ssl` — `SSLError` or any "ssl" in message
- `connection` — `ConnectionError` with sub-messages for DNS/refused/no-route/generic
- `http` — `HTTPError` (attaches `http_status`, `reason`, `response_snippet` up to 400 chars)
- `request` — catch-all

### 5.3 Check state mapping
Consistent across system and firmware checks:
- Connection/timeout/DNS errors → **UNKNOWN** (transient, not a plugin misconfig)
- SSL/HTTP/auth errors on **System** → **CRIT** (configuration problem that needs fixing)
- SSL/HTTP/auth errors on **Firmware** → **WARN** (don't let a secondary check dominate)
- Missing/malformed data → **UNKNOWN**
- Valid data, no problems → **OK**

### 5.4 Check API v2 usage (the important rules)
- **Imports:** `from cmk.agent_based.v2 import AgentSection, CheckPlugin, Service, Result, State, Metric` (+ `DiscoveryResult`, `CheckResult` for type hints).
- **`Result()` must use keyword arguments** — `Result(state=State.OK, summary="...", details="...")`. Positional args fail with `TypeError`.
- **Parse function always required** — even a pass-through should be defined explicitly.
- **Plugin variables** at module bottom:
  - `agent_section_<section_name> = AgentSection(...)`
  - `check_plugin_<plugin_name> = CheckPlugin(...)`
- **When check plugin name ≠ section name:** `CheckPlugin(..., sections=["section_name"])` (see `fortigate_webfilter_expires` → `fortigate_license`).

### 5.5 Ruleset API v1 usage
- **Imports:** `from cmk.rulesets.v1 import Title, Help` and `from cmk.rulesets.v1.form_specs import ...`
- **Rule spec var:** `rule_spec_<name> = SpecialAgent(topic=Topic.NETWORKING, name="<agent_name>", title=Title(...), parameter_form=<callable>)`
- **`name=` field is the linking key** — must match the `SpecialAgentConfig(name=...)` in `server_side_calls/`. In this plugin, both say `"fortigate"`.
- **Defensive imports** for optional form specs (see `SingleChoice` fallback to `BooleanChoice`) — good pattern to keep.

### 5.6 Server-side calls v1 usage
- **Imports:** `from cmk.server_side_calls.v1 import noop_parser, SpecialAgentConfig, SpecialAgentCommand`
- **Commands function is a generator:** `yield SpecialAgentCommand(command_arguments=[...])`
- **Hostname:** prefer `host_config.primary_ip_config.address`, fall back to `host_config.name`.
- **Passwords:** `.unsafe()` on password objects to get the plaintext for CLI args.
- **Accepts both strings and bools** for flags, defensively converting — nice pattern for backward compatibility when rulesets evolve.

### 5.7 Configuration delivery pattern (important architectural choice)
Instead of a separate check-parameters ruleset, runtime config is:
1. Collected in the **special-agent ruleset**
2. Passed to the agent via **CLI flags**
3. Injected by the agent into the **JSON payload's `config` key**
4. Read by the check plugin from `section["config"]`

**Pro:** single source of configuration, no ruleset duplication.
**Con:** config is per-host (tied to special agent rule), not per-service. You can't set different thresholds for different services on the same host without more plumbing.

This is a deliberate choice and should be documented as a template pattern. We'll mark it as **Pattern A**. Alternative **Pattern B** (separate check-parameters ruleset) should also be in the template for cases where per-service thresholds matter (e.g., the hardcoded 30/15-day thresholds in the webfilter check — see §7.1).

### 5.8 Naming conventions (implied, should be codified)
| Artifact | Pattern | Examples from code |
|---|---|---|
| Family directory | `<vendor>` or `<vendor>_<scope>` | `fortigate_firmware` |
| Agent section name | `<vendor>_<datatype>` | `fortigate_system`, `fortigate_firmware`, `fortigate_license` |
| Check plugin name | `<vendor>_<what_it_checks>` | `fortigate_system`, `fortigate_webfilter_expires` |
| Service name (displayed) | Human phrase, Title Case | "FortiGate System", "Services License" |
| Special agent / ruleset name | `<vendor>` | `fortigate` |
| Python module (agent_based/) | matches check or groups related | `fortigate.py` (2 checks), `fortigate_webfilter_expires.py` (1 check) |
| libexec script | `agent_<vendor>` | `agent_fortigate` |

---

## 6. Deployment & validation workflow (from your notes, confirmed working)

1. Edit in `/omd/sites/fvemon/work/checkmk-fortios-fw`
2. `python3 -m py_compile <file.py>` (syntax gate)
3. `rsync -av --delete --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' <repo>/local/.../fortigate_firmware/ <live>/fortigate_firmware/`
4. Clear pycache in live tree (critical — stale bytecode causes silent ghost behavior)
5. `omd restart <site>` (if rulesets, server_side_calls, or service_name changed)
6. `cmk -R` (rebuild core config)
7. `cmk -IIv <host>` (rediscover)
8. Validate: `cmk -d <host>` (raw agent output), `cmk -nv <host>` (dry-run check), `cmk -D <host>` (inspect resolved agent command)

**To be added to the workflow:** `cmk-validate-plugins` as an earlier gate between steps 2 and 3 — it's a Checkmk 2.4 native tool that catches API-misuse errors before they reach a restart.

---

## 7. Issues and smells to address

Ordered by rough priority. None are blockers; all are template-worthy improvements.

### 7.1 Hardcoded thresholds in webfilter check — **medium**
The 30/15-day WARN/CRIT thresholds in `fortigate_webfilter_expires.py` are literals. A proper implementation would add a **check-parameters ruleset** in `rulesets/` so they're GUI-configurable per host/service. Good template example for **Pattern B** (§5.7).

### 7.2 `graphing/fortigate_firmware.py` is a non-functional stub — **low**
It imports the legacy `graph_info` dict wrapped in try/except and defines nothing. Either:
- Delete it, or
- Replace with proper Graphing API v1 (`from cmk.graphing.v1 import metrics, graphs, perfometers`) to render the existing metrics (`updates_available`, `builds_behind_latest`, `days_until_webfilter_expiry`, etc.) with proper units and graphs.

Recommendation: delete now, add real graphing when we formalize the template.

### 7.3 Family name misnomer — **low but permanent**
The family is `fortigate_firmware`, but it now covers system, firmware, and license. It should really be `fortigate`. Renaming is disruptive (old MKP references, existing services), so this is a judgment call:
- **Keep** `fortigate_firmware`: zero disruption, slightly misleading forever.
- **Rename** to `fortigate`: clean, but old installs would need a migration (uninstall old MKP + install new + re-run discovery).

For the **template repo**, codify "one family per vendor, not per feature" — so future plugins don't repeat this mistake.

### 7.4 Discovery fails closed when API is down — **low**
`discover_fortigate_system` requires `status == "success"`. A brand-new host with a broken API key will never discover the service, so you never see the CRIT that would tell you the key is broken. Safer pattern: discover unconditionally if *any* section is received, let the check function report the error state.

Applies to firmware check too (it already discovers on any section, which is better).

### 7.5 Duplicated error-classification logic — **low**
The "map error_type/detail keywords to UNKNOWN vs CRIT/WARN" logic is copy-pasted between `check_fortigate_system` and `check_fortigate_firmware`. Extract into a shared helper (e.g., a `_errors.py` module in `agent_based/`). Reduces drift when rules evolve.

### 7.6 MKP metadata is stale — **trivial but visible**
`.mkp-builder.ini` says:
```
version.min_required = 2.3.0p1
version.packaged = 2.3.0p34
```
Target is 2.4.0. Bump `min_required` to `2.4.0p1` (or whichever patch level you standardize on) and update `packaged` per release.

### 7.7 `.bak` files in live tree — **trivial**
Files like `agent_fortigate.bak.2026-02-13_173424` are present in the live site directory. They don't hurt (Checkmk ignores files that don't match the expected naming), but they're clutter. Template convention: backups live outside the plugin tree or in a separate dir, never inside `local/`.

### 7.8 Bearer token visible in `ps aux` — **informational**
`--api-key <secret>` on the command line means the token is visible to anyone who can read `/proc`. Inside a dedicated site user's context this is mostly fine, but a hardened version would pass the secret via stdin or an env var. Template could offer both patterns; for now, document that the current pattern is acceptable for most deployments.

### 7.9 Minor parse inconsistency — **trivial**
`parse_fortigate_system` and `parse_fortigate_firmware` use `itertools.chain.from_iterable(string_table)` → `" ".join(...)`. `parse_fortigate_license` uses `" ".join(string_table[0])`. Both work for `:sep(0)` single-line payloads; the former is slightly more defensive. Standardize in the template.

### 7.10 Missing checkman for webfilter — **low**
`checkman/` has `fortigate_firmware` and `fortigate_system` but no `fortigate_webfilter_expires`. Add one for consistency.

---

## 8. What's good and should be preserved

- Clean separation of concerns across the 4 API layers (ruleset / SSC / agent / check).
- Defensive JSON parsing with fallback to error dict.
- Structured error payloads from agent with error-type taxonomy.
- Error handling that distinguishes transient (UNKNOWN) from configuration (CRIT) failures.
- Per-host config delivered via agent payload injection (clever Pattern A).
- Defensive imports for optional FormSpec classes.
- `_normalize_firmware_payload` to handle FortiOS version-schema drift — good shape-normalization pattern worth codifying as a template helper.
- CI workflow via `oposs/mkp-builder@v2` — works, tag → release → `.mkp` asset.
- README covers configuration and error-handling expectations.

---

## 9. Recommended template structure (preview)

Based on the above, the template repo should provide:

```
checkmk-plugin-template/
├── .github/workflows/build.yml             (copy of working CI)
├── .gitignore
├── .mkp-builder.ini.template               (to be filled per plugin)
├── CLAUDE.md                                (agent instructions — the gotchas list)
├── README.md.template
├── docs/
│   ├── ARCHITECTURE.md                     (this document, generalized)
│   ├── CONVENTIONS.md                      (§5 of this doc as rules)
│   └── PLAYBOOKS.md                        (add-service, add-plugin, validate, release)
└── local/lib/python3/cmk_addons/plugins/<FAMILY>/
    ├── agent_based/
    │   ├── _errors.py                      (shared error classifier)
    │   ├── <family>.py                     (example check, pattern A)
    │   └── <family>_example_thresholds.py  (example check, pattern B with ruleset)
    ├── checkman/
    │   └── <family>_example               (template man page)
    ├── graphing/
    │   └── <family>.py                     (proper Graphing API v1 example)
    ├── libexec/
    │   └── agent_<family>                  (template with error helper)
    ├── rulesets/
    │   ├── special_agent.py                (pattern A)
    │   └── check_params_example.py         (pattern B — per-service thresholds)
    └── server_side_calls/
        └── special_agent.py
```

The template carries **both Pattern A and Pattern B** examples so future plugins can pick the right one per service.

---

## 10. Decisions needed before Phase 2 (template build)

1. **Family renaming** — Keep `fortigate_firmware` (zero disruption) or rename to `fortigate` (clean, but requires migration)?
2. **Webfilter thresholds** — Leave hardcoded for now, or convert to Pattern B (check-parameters ruleset) as the first demonstration of Pattern B in the codebase?
3. **Graphing** — Delete the stub, or actually populate it with Graphing API v1 definitions (useful as a template example for future plugins)?
4. **Secret-passing in CLI** — Keep `--api-key <secret>` (current, simple, visible in ps), or switch to stdin/env passing (more secure, slightly more complex)?
5. **Template first, or fix-reference-plugin first?** — Two orderings:
   - (a) Build template from scratch, then port the FortiGate plugin onto it (clean but slower).
   - (b) Fix the FortiGate plugin in place (addressing §7 items), then extract the template from the result (faster, immediate production improvement, but template ends up shaped by one plugin).

My recommendation: **(b) — improve the FortiGate plugin first**, then extract the template. You get real-world pressure-testing of conventions before they get codified, and your production server benefits immediately.
