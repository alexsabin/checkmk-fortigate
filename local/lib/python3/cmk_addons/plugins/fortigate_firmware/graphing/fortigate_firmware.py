#!/usr/bin/env python3
"""Graphing definitions for the FortiGate plugin (system, firmware, license)."""

from cmk.graphing.v1 import Title, graphs, metrics

UNIT_COUNT = metrics.Unit(metrics.DecimalNotation(""), metrics.StrictPrecision(0))
UNIT_DAYS = metrics.Unit(metrics.DecimalNotation("days"), metrics.StrictPrecision(0))


# System identity metrics: declared so the validator does not warn about unknown
# metrics, but intentionally not grouped into a graph. They are encoded version
# numbers, not measurements, so a time series is a flat line that mimics data.
metric_version_numeric = metrics.Metric(
    name="version_numeric",
    title=Title("FortiOS version (encoded)"),
    unit=UNIT_COUNT,
    color=metrics.Color.GRAY,
)
metric_build_number = metrics.Metric(
    name="build_number",
    title=Title("FortiOS build number"),
    unit=UNIT_COUNT,
    color=metrics.Color.DARK_GRAY,
)

metric_updates_available = metrics.Metric(
    name="updates_available",
    title=Title("FortiOS updates available"),
    unit=UNIT_COUNT,
    color=metrics.Color.BLUE,
)
# "security_updates" is intentionally not redefined here: it is already owned by
# cmk.plugins.collection.graphing.updates (the apt plugin). The check still emits
# Metric("security_updates", ...); the upstream definition renders it.
metric_builds_behind_recommended = metrics.Metric(
    name="builds_behind_recommended",
    title=Title("Builds behind recommended"),
    unit=UNIT_COUNT,
    color=metrics.Color.GREEN,
)
metric_builds_behind_latest = metrics.Metric(
    name="builds_behind_latest",
    title=Title("Builds behind latest"),
    unit=UNIT_COUNT,
    color=metrics.Color.RED,
)
metric_major_versions_behind = metrics.Metric(
    name="major_versions_behind",
    title=Title("Major versions behind"),
    unit=UNIT_COUNT,
    color=metrics.Color.DARK_RED,
)
metric_minor_versions_behind = metrics.Metric(
    name="minor_versions_behind",
    title=Title("Minor versions behind"),
    unit=UNIT_COUNT,
    color=metrics.Color.LIGHT_ORANGE,
)

metric_days_until_webfilter_expiry = metrics.Metric(
    name="days_until_webfilter_expiry",
    title=Title("Days until web filter license expiry"),
    unit=UNIT_DAYS,
    color=metrics.Color.PURPLE,
)


graph_fortigate_firmware_updates_available = graphs.Graph(
    name="fortigate_firmware_updates_available",
    title=Title("FortiOS updates available"),
    simple_lines=["updates_available"],
)

graph_fortigate_firmware_builds_behind = graphs.Graph(
    name="fortigate_firmware_builds_behind",
    title=Title("FortiOS builds behind"),
    simple_lines=["builds_behind_recommended", "builds_behind_latest"],
    optional=["builds_behind_recommended", "builds_behind_latest"],
)

graph_fortigate_firmware_versions_behind = graphs.Graph(
    name="fortigate_firmware_versions_behind",
    title=Title("FortiOS versions behind"),
    simple_lines=["major_versions_behind", "minor_versions_behind"],
    optional=["major_versions_behind", "minor_versions_behind"],
)

graph_fortigate_webfilter_expiry_days = graphs.Graph(
    name="fortigate_webfilter_expiry_days",
    title=Title("Days until web filter license expiry"),
    simple_lines=["days_until_webfilter_expiry"],
)
