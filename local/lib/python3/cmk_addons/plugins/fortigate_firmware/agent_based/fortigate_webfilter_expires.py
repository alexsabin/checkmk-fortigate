from __future__ import annotations

import itertools
import json
import time
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    DiscoveryResult,
    CheckResult,
    Metric,
    Result,
    Service,
    State,
)

Section = Mapping[str, Any]


def _parse_single_json_line(string_table) -> Dict[str, Any]:
    # With :sep(0) the payload comes as a JSON line; join defensively.
    if not string_table:
        return {}
    line = " ".join(itertools.chain.from_iterable(string_table))
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def parse_fortigate_license(string_table) -> Dict[str, Any]:
    return _parse_single_json_line(string_table)


agent_section_fortigate_license = AgentSection(
    name="fortigate_license",
    parse_function=parse_fortigate_license,
)


def discover_fortigate_webfilter_expires(section: Section) -> DiscoveryResult:
    if section:
        yield Service()


def _get_expires_epoch(section: Section) -> Optional[int]:
    wf = section.get("web_filtering")
    if not isinstance(wf, dict):
        return None
    expires = wf.get("expires")
    try:
        return int(expires)
    except Exception:
        return None


def check_fortigate_webfilter_expires(params: Mapping[str, Any], section: Section) -> CheckResult:
    wf = section.get("web_filtering")
    if not isinstance(wf, dict):
        yield Result(state=State.UNKNOWN, summary="No web_filtering data in agent output")
        return

    status = wf.get("status") or "unknown"
    expires = _get_expires_epoch(section)
    if not expires or expires <= 0:
        yield Result(state=State.UNKNOWN, summary=f"Webfilter expiry missing/invalid (status: {status})")
        return

    now = int(time.time())
    seconds_left = expires - now
    days_left = seconds_left // 86400

    expiry_local = datetime.fromtimestamp(expires).astimezone()
    expiry_str = expiry_local.strftime("%Y-%m-%d")

    if seconds_left <= 0:
        yield Result(state=State.CRIT, summary=f"Expired on {expiry_str} ({abs(days_left)} days ago) (status: {status})")
    elif days_left <= params["crit_days"]:
        yield Result(state=State.CRIT, summary=f"Expires in {days_left} days ({expiry_str}) (status: {status})")
    elif days_left <= params["warn_days"]:
        yield Result(state=State.WARN, summary=f"Expires in {days_left} days ({expiry_str}) (status: {status})")
    else:
        yield Result(state=State.OK, summary=f"Expires in {days_left} days ({expiry_str}) (status: {status})")

    yield Metric("days_until_webfilter_expiry", float(days_left))


check_plugin_fortigate_webfilter_expires = CheckPlugin(
    name="fortigate_webfilter_expires",
    service_name="Services License",
    sections=["fortigate_license"],
    discovery_function=discover_fortigate_webfilter_expires,
    check_function=check_fortigate_webfilter_expires,
    check_default_parameters={"warn_days": 30, "crit_days": 15},
    check_ruleset_name="fortigate_webfilter_expires",
)
