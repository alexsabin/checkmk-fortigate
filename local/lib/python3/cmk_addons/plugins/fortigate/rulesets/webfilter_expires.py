#!/usr/bin/env python3
# Shebang needed only for editors

from cmk.rulesets.v1 import Title, Help
from cmk.rulesets.v1.form_specs import (
    DefaultValue,
    DictElement,
    Dictionary,
    Integer,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostCondition, Topic


def _parameter_form():
    return Dictionary(
        title=Title("FortiGate Services License expiry thresholds"),
        help_text=Help(
            "Day thresholds for the FortiGate Services License (web filtering) check. "
            "WARN is raised when the remaining days fall to or below the warning value; "
            "CRIT is raised when they fall to or below the critical value, or once the "
            "license has already expired."
        ),
        elements={
            "warn_days": DictElement(
                required=True,
                parameter_form=Integer(
                    title=Title("Warning at or below"),
                    help_text=Help("Days remaining before expiry (default 30)."),
                    prefill=DefaultValue(30),
                ),
            ),
            "crit_days": DictElement(
                required=True,
                parameter_form=Integer(
                    title=Title("Critical at or below"),
                    help_text=Help("Days remaining before expiry (default 15)."),
                    prefill=DefaultValue(15),
                ),
            ),
        },
    )


rule_spec_fortigate_webfilter_expires = CheckParameters(
    name="fortigate_webfilter_expires",
    topic=Topic.NETWORKING,
    parameter_form=_parameter_form,
    title=Title("FortiGate Services License expiry thresholds"),
    condition=HostCondition(),
)
