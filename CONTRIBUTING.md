# Contributing

Notes for hacking on this plugin. Two parts: a dev loop portable to any Checkmk 2.4 plugin project, and a list of Checkmk gotchas that are easy to miss.

## Dev loop (template-portable)

Shape of the loop: edit a file, run `./scripts/deploy-test.sh`, inspect via the `cmk` triad, repeat.

### Test container

A clean Checkmk 2.4 raw container is the iteration target:

```bash
docker run -d --name cmk-test -p 8080:5000 \
  -e CMK_PASSWORD=<password> \
  checkmk/check-mk-raw:2.4.0-latest
```

Site name is `cmk` (the raw image's default). GUI: `http://localhost:8080/cmk/`. Inside the container, the site user is `cmk`.

### Deploy script

`./scripts/deploy-test.sh` syncs the local plugin tree into `/omd/sites/cmk/local/lib/python3/cmk_addons/plugins/<family>/` inside the container, clears pycache, runs `cmk-validate-plugins`, and restarts what's needed:

- `--full` — force `omd restart` (used when rulesets, server-side calls, or graphing changed).
- `--reload` — force `cmk -R` only (used when only check logic or the agent changed).
- no flag — auto-detect by hashing the GUI-affecting subdirectories.

If `cmk-validate-plugins` reports issues the script exits non-zero. Fix the validation error before doing anything else; do not deploy around it.

### Inspection triad

After deploy, three commands form the bring-up triad:

| Command | What it tells you |
|---|---|
| `cmk -d <host>` | Raw agent output. Ground truth for what the plugin sees. |
| `cmk -nv <host>` | Dry-run check evaluation. Computes service states without touching the RRD. |
| `cmk -D <host>` | Resolved special-agent command line, plus the host's discovered services with their resolved check parameters. |

Run them inside the container as the site user:

```bash
docker exec -u cmk cmk-test bash -lc 'cmk -d <host>'
docker exec -u cmk cmk-test bash -lc 'cmk -nv <host>'
docker exec -u cmk cmk-test bash -lc 'cmk -D <host>'
```

### Baseline services

This project tracks a known-good set of services on the test host (`fw-test`): **FortiGate System**, **FortiGate Firmware Updates**, **Services License**. After any edit, all three must still be discovered with their pre-edit state. `cmk -D <host>` lists discovered services and is the cheapest check.

For other Checkmk plugin projects: identify the equivalent always-present service set on your test host and re-verify after every edit.

## Checkmk plugin gotchas

Facts about the Checkmk 2.4 APIs that bit hard enough to write down. Project-agnostic.

### Agent section separator

JSON section payloads must declare `:sep(0)` on the section header:

```
<<<fortigate_system:sep(0)>>>
{"status": "success", ...}
```

Without `:sep(0)` Checkmk uses the default whitespace tokenizer on the JSON line, splitting on each space — the parse function gets a `string_table` of token fragments instead of one JSON line. Symptoms: parse silently returns `None`, services discover but report UNKNOWN or missing.

### `Result()` is kwargs-only

```python
yield Result(state=State.OK, summary="...", details="...")  # correct
yield Result(State.OK, "...", "...")                        # raises TypeError
```

The Check API v2 enforces keyword arguments. Positional calls fail at import time.

### `__pycache__` and `*.pyc` after every edit

Stale bytecode in `local/lib/python3/cmk_addons/plugins/<family>/` produces silent ghost behavior — old check logic continues to run while the new source sits unused. The deploy script clears caches automatically. If you bypass the script (e.g. editing inside the container), clear them by hand:

```bash
find local/lib/python3/cmk_addons/plugins/<family> \
  -name '__pycache__' -type d -exec rm -rf {} +
find local/lib/python3/cmk_addons/plugins/<family> \
  -name '*.pyc' -delete
```

### `libexec/` executable bit

Special-agent scripts in `libexec/` must be mode 755. Copy operations (`docker cp`, `rsync` without `--chmod`, archive extraction) can drop the bit. Symptoms: `cmk -d <host>` returns nothing useful and the underlying process exits 126 (permission denied). The deploy script re-applies `chmod 755` after copying into the container; if you bypass the script, restore it by hand:

```bash
chmod 755 local/lib/python3/cmk_addons/plugins/<family>/libexec/agent_*
```
