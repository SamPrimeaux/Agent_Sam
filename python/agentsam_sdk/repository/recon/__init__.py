"""Bounded recon-worker harness: task-packet construction and finding-report validation.

This module does not call any model. It is the deterministic controller half of the
recon protocol described in docs/RECON.md — building small, exact, already-scoped work
packets, and validating whatever a worker (local or hosted) sends back against hard
ceilings before it reaches a capable coding agent.
"""
from .packet import (
    build_task_packet,
    from_matches,
    from_ast_grep,
    from_ripgrep,
    PacketError,
    TOOL_NAME_PACK,
)
from .validate import validate_report, ReportError, TOOL_NAME_VALIDATE

__all__ = [
    "build_task_packet",
    "from_matches",
    "from_ast_grep",
    "from_ripgrep",
    "PacketError",
    "TOOL_NAME_PACK",
    "validate_report",
    "ReportError",
    "TOOL_NAME_VALIDATE",
]
