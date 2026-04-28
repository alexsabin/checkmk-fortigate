"""Shared error-classification constants for FortiGate check functions."""

# Matched against err_type / message / detail to route an agent error payload
# to UNKNOWN (transient) rather than CRIT/WARN (configuration/protocol).
unknown_hints = [
    "no route to host",
    "failed to connect",
    "failed to establish",
    "dns",
    "resolution",
    "refused",
    "timed out",
    "timeout",
]
