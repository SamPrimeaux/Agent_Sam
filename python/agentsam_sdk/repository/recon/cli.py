"""CLI and ToolInput adapter for the recon bounded-worker harness.

Two read-only operations, matching the controller/validator halves of the pipeline
described in docs/RECON.md:

    python -m agentsam_sdk.repository.recon pack --repo-root . \\
        --question "..." --slice backend/workflows/repository/workflows.js:1-180 \\
        --out packet.json

    python -m agentsam_sdk.repository.recon validate --packet packet.json \\
        --report report.json

Neither operation calls a model. `pack` is the deterministic controller step;
`validate` is the deterministic gate a worker's report must pass before a capable
agent ever sees it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentsam_sdk.runtime.contract import ToolInput, ToolResult, start_timer, write_receipt

from .packet import TOOL_NAME_PACK, build_task_packet
from .validate import TOOL_NAME_VALIDATE, ReportError, validate_report


def _parse_slice_arg(raw: str) -> dict[str, str | int]:
    # path[:start-end]
    if ":" in raw:
        path, rng = raw.rsplit(":", 1)
        if "-" in rng:
            start, end = rng.split("-", 1)
            return {"path": path, "start_line": int(start), "end_line": int(end)}
    return {"path": raw}


def run_pack(tool_input: ToolInput) -> ToolResult:
    started = start_timer()
    try:
        tool_input.assert_read_only()
        params = tool_input.params
        packet = build_task_packet(
            params.get("repo_root") or ".",
            question=params["question"],
            slices=params.get("slices") or [],
            task_id=params.get("task_id"),
            allowed_diagnostics=params.get("allowed_diagnostics") or (),
            max_follow_up_reads=int(params.get("max_follow_up_reads", 2)),
            max_output_tokens=int(params.get("max_output_tokens", 800)),
            timeout_seconds=int(params.get("timeout_seconds", 90)),
        )
        artifacts: list[str] = []
        output_dir = tool_input.output_path()
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            out = output_dir / f"recon-packet-{packet['task_id']}.json"
            out.write_text(json.dumps(packet, indent=2), encoding="utf-8")
            artifacts.append(str(out))
        result = ToolResult(
            ok=True,
            tool=TOOL_NAME_PACK,
            mode=tool_input.mode or "read-only",
            request_id=tool_input.request_id,
            started_at=started,
            finished_at=start_timer(),
            summary=f"Built bounded task packet {packet['task_id']} ({len(packet['slices'])} slice(s)).",
            data=packet,
            artifacts=artifacts,
        )
    except Exception as exc:  # noqa: BLE001 - normalized into ToolResult
        result = ToolResult(
            ok=False,
            tool=TOOL_NAME_PACK,
            mode=tool_input.mode or "read-only",
            request_id=tool_input.request_id,
            started_at=started,
            finished_at=start_timer(),
            summary="recon pack failed",
            error=str(exc)[:500],
        )
    write_receipt(result, tool_input.output_path())
    return result


def run_validate(tool_input: ToolInput) -> ToolResult:
    started = start_timer()
    try:
        tool_input.assert_read_only()
        params = tool_input.params
        packet = params["packet"]
        report = params["report"]
        try:
            validated = validate_report(report, packet)
            ok = True
            summary = f"Report for {report.get('task_id')} is valid ({report.get('status')})."
            error = None
        except ReportError as exc:
            validated = {}
            ok = False
            summary = "Report rejected; do not forward to the capable agent."
            error = str(exc)
        result = ToolResult(
            ok=ok,
            tool=TOOL_NAME_VALIDATE,
            mode=tool_input.mode or "read-only",
            request_id=tool_input.request_id,
            started_at=started,
            finished_at=start_timer(),
            summary=summary,
            data={"validated_report": validated} if ok else {},
            error=error,
        )
    except Exception as exc:  # noqa: BLE001 - normalized into ToolResult
        result = ToolResult(
            ok=False,
            tool=TOOL_NAME_VALIDATE,
            mode=tool_input.mode or "read-only",
            request_id=tool_input.request_id,
            started_at=started,
            finished_at=start_timer(),
            summary="recon validate failed",
            error=str(exc)[:500],
        )
    write_receipt(result, tool_input.output_path())
    return result


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agentsam_sdk.repository.recon",
        description="Build bounded recon task packets and validate worker findings.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pack_p = sub.add_parser("pack", help="Build a bounded ReconTaskPacket.")
    pack_p.add_argument("--repo-root", default=".")
    pack_p.add_argument("--question", required=True)
    pack_p.add_argument(
        "--slice", dest="slices", action="append", default=[],
        help="path[:start-end], repeatable, up to 5.",
    )
    pack_p.add_argument("--task-id")
    pack_p.add_argument("--out")

    validate_p = sub.add_parser("validate", help="Validate a ReconFindingReport against its packet.")
    validate_p.add_argument("--packet", required=True, help="Path to a packet JSON file.")
    validate_p.add_argument("--report", required=True, help="Path to a report JSON file.")

    args = parser.parse_args(argv)

    if args.command == "pack":
        packet = build_task_packet(
            args.repo_root,
            question=args.question,
            slices=[_parse_slice_arg(s) for s in args.slices],
            task_id=args.task_id,
        )
        rendered = json.dumps(packet, indent=2)
        if args.out:
            Path(args.out).expanduser().write_text(rendered, encoding="utf-8")
        else:
            print(rendered)
        return 0

    if args.command == "validate":
        packet = json.loads(Path(args.packet).expanduser().read_text(encoding="utf-8"))
        report = json.loads(Path(args.report).expanduser().read_text(encoding="utf-8"))
        try:
            validate_report(report, packet)
        except ReportError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1
        print(json.dumps({"ok": True}, indent=2))
        return 0

    return 2
