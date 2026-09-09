"""Build a bounded ReconTaskPacket from an explicit repo root and an explicit file list.

Design law (mirrors protocol/README.md rule 6 and docs/REPOSITORY_INTELLIGENCE.md):
  - Read-only. This module never writes into the target repository.
  - Accepts an explicit repo_root; never assumes one repository's layout.
  - Never hardcodes a tenant/workspace/provider ID as the task handle.
  - The caller (a capable agent, or repository.intelligence output) selects the files.
    This module does not go searching for "relevant" files on its own — that discovery
    step belongs upstream, where budget and reasoning are cheap.

Stdlib only.
"""
from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
TOOL_NAME_PACK = "repository.recon.pack"
MAX_SLICES = 5
MAX_FOLLOW_UP_READS = 2
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_MAX_OUTPUT_TOKENS = 800


class PacketError(ValueError):
    """Raised when a task packet cannot be built as specified."""


def _head_sha(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8", errors="surrogateescape").strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def _read_slice(repo_root: Path, rel_path: str, start_line: int | None, end_line: int | None) -> str:
    target = (repo_root / rel_path).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise PacketError(f"slice_escapes_repo_root:{rel_path}") from exc
    if not target.is_file():
        raise PacketError(f"slice_not_found:{rel_path}")
    try:
        text = target.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError) as exc:
        raise PacketError(f"slice_unreadable:{rel_path}") from exc
    if start_line is None and end_line is None:
        return text
    lines = text.splitlines()
    start = max(1, start_line or 1)
    end = min(len(lines), end_line or len(lines))
    if start > end:
        raise PacketError(f"slice_range_invalid:{rel_path}:{start}-{end}")
    return "\n".join(lines[start - 1 : end])


def build_task_packet(
    repo_root: str | Path,
    *,
    question: str,
    slices: Iterable[dict[str, Any]],
    task_id: str | None = None,
    allowed_diagnostics: Iterable[str] = (),
    max_follow_up_reads: int = MAX_FOLLOW_UP_READS,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    embed_content: bool = True,
) -> dict[str, Any]:
    """Build one bounded ReconTaskPacket.

    `slices` is a list of {"path", "start_line"?, "end_line"?, "reason"?} — exact,
    caller-chosen material. This function never expands that list; it only reads and
    validates it, and enforces the hard ceilings from protocol/recon/task-packet.schema.json.
    """
    root = Path(repo_root).expanduser().resolve()
    if not root.is_dir():
        raise PacketError(f"repo_root_not_found:{root}")
    if not question or not question.strip():
        raise PacketError("question_required")

    slice_list = list(slices)
    if not slice_list:
        raise PacketError("at_least_one_slice_required")
    if len(slice_list) > MAX_SLICES:
        raise PacketError(f"too_many_slices:{len(slice_list)}>{MAX_SLICES}")
    if not (0 <= max_follow_up_reads <= MAX_FOLLOW_UP_READS):
        raise PacketError(f"max_follow_up_reads_out_of_range:{max_follow_up_reads}")

    resolved_slices: list[dict[str, Any]] = []
    for item in slice_list:
        path = item.get("path")
        if not path:
            raise PacketError("slice_missing_path")
        start_line = item.get("start_line")
        end_line = item.get("end_line")
        entry: dict[str, Any] = {"path": path}
        if start_line is not None:
            entry["start_line"] = int(start_line)
        if end_line is not None:
            entry["end_line"] = int(end_line)
        if item.get("reason"):
            entry["reason"] = str(item["reason"])
        if item.get("kind"):
            entry["kind"] = str(item["kind"])
        if item.get("hit_count"):
            entry["hit_count"] = int(item["hit_count"])
        if embed_content:
            entry["content"] = _read_slice(root, path, entry.get("start_line"), entry.get("end_line"))
        resolved_slices.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id or f"recon-{uuid.uuid4().hex[:12]}",
        "repo_root": str(root),
        "base_sha": _head_sha(root),
        "generated_at_unix": int(time.time()),
        "question": question.strip(),
        "slices": resolved_slices,
        "allowed_diagnostics": list(allowed_diagnostics),
        "ceilings": {
            "max_follow_up_reads": max_follow_up_reads,
            "max_output_tokens": max_output_tokens,
            "timeout_seconds": timeout_seconds,
        },
        "response_schema_ref": "./finding-report.schema.json",
    }


def from_matches(
    repo_root: str | Path,
    *,
    question: str,
    matches: Iterable[dict[str, Any]],
    task_id_prefix: str = "recon",
    max_files_per_packet: int = MAX_SLICES,
    context_lines: int = 3,
    **packet_kwargs: Any,
) -> list[dict[str, Any]]:
    """Turn raw, tool-agnostic search hits into one or more bounded packets.

    This is the adapter for "I already ran rg/ast-grep and have a hit list, now I
    need packets" -- it does not run any search itself. `matches` is any iterable of
    {"path": str, "line": int, "kind": str?} -- output from from_ripgrep()/from_ast_grep()
    (or any hand-built equivalent) works directly.

    Hits are grouped by file into one slice per file (a [min-context, max+context]
    line window covering every hit in that file), then chunked into packets of at
    most `max_files_per_packet` files each -- so a 16-file, 41-hit sweep becomes
    several small packets instead of one that violates the slice ceiling or silently
    drops files.

    The worker still never searches. This function is what the controller runs
    *instead of* handing the worker rg.
    """
    if max_files_per_packet > MAX_SLICES:
        raise PacketError(f"max_files_per_packet_exceeds_ceiling:{max_files_per_packet}>{MAX_SLICES}")

    by_path: dict[str, dict[str, Any]] = {}
    for hit in matches:
        path = hit.get("path")
        if not path:
            raise PacketError("match_missing_path")
        line = hit.get("line")
        entry = by_path.setdefault(path, {"lines": [], "kinds": set()})
        if line is not None:
            entry["lines"].append(int(line))
        if hit.get("kind"):
            entry["kinds"].add(str(hit["kind"]))

    if not by_path:
        raise PacketError("no_matches_supplied")

    files = sorted(by_path)
    packets: list[dict[str, Any]] = []
    chunks = [files[i : i + max_files_per_packet] for i in range(0, len(files), max_files_per_packet)]
    for idx, chunk in enumerate(chunks, start=1):
        slices = []
        for path in chunk:
            entry = by_path[path]
            lines = entry["lines"]
            if lines:
                start = max(1, min(lines) - context_lines)
                end = max(lines) + context_lines
            else:
                start = end = None
            kinds = sorted(entry["kinds"])
            reason = f"{len(lines) or 'unknown-count of'} hit(s)"
            if kinds:
                reason += f" ({', '.join(kinds)})"
            slice_entry: dict[str, Any] = {"path": path, "reason": reason}
            if start is not None:
                slice_entry["start_line"] = start
                slice_entry["end_line"] = end
            if lines:
                slice_entry["hit_count"] = len(lines)
            if len(kinds) == 1:
                slice_entry["kind"] = kinds[0]
            slices.append(slice_entry)
        suffix = f"-{idx}of{len(chunks)}" if len(chunks) > 1 else ""
        packets.append(
            build_task_packet(
                repo_root,
                question=question,
                slices=slices,
                task_id=f"{task_id_prefix}{suffix}",
                **packet_kwargs,
            )
        )
    return packets


def from_ripgrep(rg_json: str | Iterable[str]) -> list[dict[str, Any]]:
    """Parse `rg --json` NDJSON output into `from_matches()`-shaped hits.

    Runs no search itself -- pass the captured stdout of an `rg --json ...` call
    (a single string, or an iterable of its lines). Only `type: "match"` records are
    kept. rg is lexical only, so hits carry no `kind` -- pair with `from_ast_grep()`
    output in the same `matches` list when structural classification is available.

    Example::

        raw = subprocess.run(
            ["rg", "--json", "-e", "workspace_id", "backend/workflows"],
            capture_output=True, text=True,
        ).stdout
        matches = recon.from_ripgrep(raw)
    """
    lines = rg_json.splitlines() if isinstance(rg_json, str) else rg_json
    hits: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PacketError(f"rg_json_line_invalid:{line[:80]}") from exc
        if obj.get("type") != "match":
            continue
        data = obj.get("data", {})
        path = (data.get("path") or {}).get("text")
        line_number = data.get("line_number")
        if not path or line_number is None:
            continue
        hits.append({"path": path, "line": int(line_number)})
    return hits


def from_ast_grep(sg_json_compact: str, *, kind: str | None = None) -> list[dict[str, Any]]:
    """Parse `sg`/`ast-grep ... --json=compact` array output into `from_matches()`-shaped hits.

    Runs no search itself. One ast-grep invocation is one pattern or one inline rule --
    i.e. one structural shape -- so `kind` is a caller-supplied label applied to every
    hit from that call (e.g. "member", "member_camel", "sql_string"), not something
    this function infers. Redirect the deprecation banner ast-grep prints on stderr
    away from stdout (it does not appear in --json=compact stdout, but callers piping
    `2>&1` will see it mixed in).

    Example::

        raw = subprocess.run(
            ["sg", "-p", "$X.workspace_id", "-l", "js", "--json=compact",
             "backend/workflows"],
            capture_output=True, text=True,
        ).stdout
        matches = recon.from_ast_grep(raw, kind="member")
    """
    text = sg_json_compact.strip()
    if not text:
        return []
    try:
        records = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PacketError(f"sg_json_invalid:{text[:80]}") from exc
    hits: list[dict[str, Any]] = []
    for record in records:
        path = record.get("file")
        line_number = ((record.get("range") or {}).get("start") or {}).get("line")
        if not path or line_number is None:
            continue
        hit: dict[str, Any] = {"path": path, "line": int(line_number)}
        if kind:
            hit["kind"] = kind
        hits.append(hit)
    return hits
