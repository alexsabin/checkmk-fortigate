#!/usr/bin/env python3
# Shebang needed only for editors

from cmk.server_side_calls.v1 import noop_parser, SpecialAgentConfig, SpecialAgentCommand


def _agent_arguments(params, host_config):
    """Genera gli argomenti per l'esecuzione dello special agent"""
    args = [
        "--hostname", host_config.primary_ip_config.address or host_config.name,
        "--api-key", params["api_key"].unsafe(),
    ]
    # Parametri opzionali
    # Branch upgrade handling (supports: 'critical', 'warn', 'ok'; also accepts bool for backward-compat)
    crit_param = params.get("critical_on_branch_change", "critical")
    if isinstance(crit_param, bool):
        mode = "critical" if crit_param else "warn"
    else:
        mode = str(crit_param).strip().lower()

    if mode in ("critical", "crit", "c", "true", "yes", "on", "1"):
        args.append("--branch-change-critical")
    else:
        args.append("--no-branch-change-critical")
        if mode in ("ok", "ok_info", "info"):
            args.append("--branch-change-ok")
    ok_param = params.get("ok_if_unmatured_branch", False)
    if isinstance(ok_param, str):
        ok_flag = ok_param.lower() in ("true", "yes", "on", "1")
    else:
        ok_flag = bool(ok_param)

    if ok_flag:
        args.append("--ok-if-unmatured-branch")

    if "port" in params:
        args.extend(["--port", str(params["port"])])

    if "timeout" in params:
        args.extend(["--timeout", str(params["timeout"])])

    yield SpecialAgentCommand(command_arguments=args)


special_agent_fortigate_firmware = SpecialAgentConfig(
    name="fortigate",
    parameter_parser=noop_parser,
    commands_function=_agent_arguments,
)
