# FortiGate Monitoring for Checkmk

Checkmk 2.4 plugin that monitors FortiGate firewalls via the FortiOS REST API. Three services per host: device health, firmware-update status, and Services License (web-filtering subscription) expiry.

## Services

| Service | What it reports |
|---|---|
| FortiGate System | Device version, build, model, serial. State reflects API reachability and authentication. |
| FortiGate Firmware Updates | Available firmware images, builds behind latest/recommended, branch-change severity. |
| Services License | Days remaining until the web-filtering subscription expires. Configurable thresholds. |

## Requirements

- Checkmk 2.4.0p1 or newer.
- HTTPS reachability to the FortiGate (default port 443; configurable).
- A FortiGate REST API token with read access to `/api/v2/monitor/system/*` and `/api/v2/monitor/license/status`. Create it on the FortiGate under **System → Administrators** with a read-only profile.

## Installation

### Production site

1. Download the latest `.mkp` from the [Releases page](https://github.com/alexsabin/checkmk-fortigate/releases).
2. Install via the Checkmk GUI: **Setup → Maintenance → Extension packages → Upload package**, then enable the new entry. Or via CLI on the site: `omd su <site>`, then `mkp add <file.mkp>` and `mkp enable fortigate <version>`.
3. Activate changes (**Activate changes** in the GUI, or `cmk -R` from the CLI).

### Evaluation in a throwaway container

For first-time evaluation, a Checkmk 2.4 raw container:

```bash
docker run -d --name cmk-test -p 8080:5000 \
  -e CMK_PASSWORD=<password> \
  checkmk/check-mk-raw:2.4.0-latest
```

GUI: `http://localhost:8080/cmk/` (login `cmkadmin` / `<password>`). Once the container is up, follow the production install steps above against the `cmk` site inside it.

## Configuration

### 1. Special-agent rule

In Checkmk **Setup**, search for **FortiGate Firmware** and add a rule.

| Field | Required | Default | Notes |
|---|---|---|---|
| API key | yes | — | The token created on the FortiGate. Can be entered inline on the rule, or selected from Checkmk's password store. |
| Branch upgrade severity | no | Critical | How to rate availability of a newer FortiOS branch (e.g. 7.4 → 7.6) when the current branch is up to date. Choices: Critical / Warn / OK. |
| OK when only immature branch upgrades exist | no | off | Stay OK if the installed firmware is the newest in its branch and all newer branches only offer immature images. |
| HTTPS port | no | 443 | |
| Connection timeout (s) | no | 30 | |

Bind the rule to the FortiGate host(s), run service discovery, and accept the three new services.

### 2. (Optional) Override Services License thresholds

Default thresholds: WARN at 30 days remaining, CRIT at 15 days. To change per host or host group, in Checkmk **Setup** search for **FortiGate Services License expiry thresholds** and add a rule.

| Field | Default | Notes |
|---|---|---|
| Warning at or below | 30 | Days remaining before expiry. WARN once `days_left ≤ warn_days`. |
| Critical at or below | 15 | Days remaining before expiry. CRIT once `days_left ≤ crit_days`, or once already expired. |

Activating changes applies the new thresholds; no special-agent restart needed.

## Service state semantics

### FortiGate System

- **OK** — API reached, system status returned successfully.
- **CRIT** — Authentication, TLS, or HTTP error. Indicates a configuration problem (bad or revoked API key, wrong port, untrusted TLS).
- **UNKNOWN** — Connection, timeout, or DNS failure. Treated as transient.

### FortiGate Firmware Updates

- **OK** — Firmware up to date, or a newer branch exists but the rule's branch-change severity keeps the state OK.
- **WARN** — Builds behind the recommended or latest image, branch upgrade available (per the rule's severity setting), or SSL/HTTP/auth error on this secondary check.
- **CRIT** — Major-version or multi-build gap, depending on rule configuration.
- **UNKNOWN** — Connection, timeout, or DNS failure.

### Services License

- **OK** — Days remaining > warn threshold.
- **WARN** — Days remaining ≤ warn threshold and > crit threshold.
- **CRIT** — Days remaining ≤ crit threshold, or license already expired.
- **UNKNOWN** — License data missing or malformed in the API response.

The summary line includes the expiry date and the days-left count.

## Troubleshooting

### One or more services missing after discovery

Re-run **Setup → Hosts → [host] → Service discovery**. The agent emits a structured error payload (rather than failing) on auth or network errors, so even with a broken API key all three services should appear with CRIT or UNKNOWN states rather than vanish. If they vanish anyway, the most likely causes are: (a) the special-agent rule does not match the host, or (b) `libexec/agent_fortigate` lost its executable bit. Run `cmk -D <host>` to inspect the resolved agent command.

### Service stuck in UNKNOWN

Run `cmk -d <host>` to see the raw agent output. The error payload (`status: "error"`, `error: <category>`, `message`, `endpoint`, `detail`) categorizes the failure. UNKNOWN is reserved for transient classes (timeout, DNS, connection refused); CRIT on System or WARN on Firmware Updates is for SSL, HTTP, or auth errors.

### HTTP 429 Too Many Requests

The FortiGate's WAF rate-limits authentication failures. After repeated bad-credential probes (e.g. during initial setup with a wrong key), expect 60–90 seconds of 429 responses before normal traffic resumes.

### GUI doesn't reflect a recent edit (developers)

See `CONTRIBUTING.md`.

## License

GPL-3.0. See `LICENSE`.
