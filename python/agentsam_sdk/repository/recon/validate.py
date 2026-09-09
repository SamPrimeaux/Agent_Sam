"""Validate a worker's ReconFindingReport against its originating packet.

This is the deterministic validator in the pipeline:
    controller -> packet -> mini worker -> [this module] -> capable agent

It does not trust the worker. It checks structure, checks that every referenced file
was actually inside the packet's slices (a worker cannot invent evidence for a file it
was never given), and enforces the "never guess" rule: a report that isn't clearly
`answered` or `needs_context` is rejected rather than passed upstream.

Stdlib only.
"""
from __future__ import annotations

from typing import Any

TOOL_NAME_VALIDATE = "repository.recon.validate"
REQUIRED_TOP_LEVEL = ("schema_version", "task_id", "status")
VALID_STATUSES = ("answered", "needs_context")
VALID_SEVERITIES = ("low", "medium", "high")


class ReportError(ValueError):
    """Raised when a finding report fails validation and must not be forwarded."""


def _known_paths(packet: dict[str, Any]) -> set[str]:
    return {s["path"] for s in packet.get("slices", [])}


def validate_report(report: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Return the report unchanged if valid; raise ReportError otherwise.

    Callers should treat a ReportError as "discard this worker output, do not hand it
    to the capable agent" — never as something to silently patch and pass along.
    """
    if not isinstance(report, dict):
        raise ReportError("report_not_an_object")

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in report]
    if missing:
        raise ReportError(f"missing_fields:{','.join(missing)}")

    if report.get("schema_version") != 1:
        raise ReportError(f"unsupported_schema_version:{report.get('schema_version')}")

    if report.get("task_id") != packet.get("task_id"):
        raise ReportError("task_id_mismatch")

    status = report.get("status")
    if status not in VALID_STATUSES:
        raise ReportError(f"invalid_status:{status}")

    if status == "needs_context":
        if not report.get("reason"):
            raise ReportError("needs_context_missing_reason")
        return report

    # status == "answered"
    known = _known_paths(packet)
    for finding in report.get("findings", []):
        for key in ("severity", "file", "finding"):
            if key not in finding:
                raise ReportError(f"finding_missing_field:{key}")
        if finding["severity"] not in VALID_SEVERITIES:
            raise ReportError(f"invalid_severity:{finding['severity']}")
        if finding["file"] not in known:
            raise ReportError(
                f"finding_cites_file_outside_packet:{finding['file']}"
            )

    for path in report.get("affected_files", []):
        if path not in known:
            raise ReportError(f"affected_file_outside_packet:{path}")

    return report
