# Recon: bounded-worker harness (aka "MiniCodeScout")

A cheap or local model (Ollama/Qwen-class, a mini-tier hosted model, whatever's
cheapest that week) can be useful as a **reconnaissance subagent** — but only once
the evidence handed to it is already disambiguated. Live investigation on the
`feat/workflow-runtime-v2` worktree found the actual failure mode wasn't missing
ceilings, it was mixed-signal evidence: a flat `rg 'workspace_id'` sweep conflates
a JS member access (`authUser?.workspace_id`), an object key (`workspace_id: ctx.workspaceId`),
and a SQL template literal (`` `AND workspace_id = ?` ``) into one undifferentiated
hit list. That's why a Qwen-class mini guessed — not because it lacked a schema.

**Current status:** the mini-worker step is benched for this sprint (decision:
`workflows-v2:ollama-benched`; follow-up tracked as backlog P3). Deterministic
search alone (`rg` today, `ast-grep` once installed) is already answering the
questions that matter, faster and for free. This kit ships as reusable infra
ahead of need — it isn't on the critical path for Workflows v2, and nothing here
should be read as "go delegate to Ollama now."

## Where recon actually starts

Recon is the last two stages of a longer pipeline, not the whole thing:

```text
lexical search (rg)         "where is this text?"          — do this first, always
        |
structural search (ast-grep, not yet installed)
        |                   "where is this shape, and which kind?"
        v
   raw hits: {path, line, kind?}
        |
        v
agentsam_sdk.repository.recon.from_matches(...)
        |                   groups by file, windows context lines,
        |                   chunks into packets of <=5 files each
        v
   ReconTaskPacket(s)   (protocol/recon/task-packet.schema.json)
        |
        v
     mini worker          (only if/when actually delegated -- never given rg)
        |
        v
   ReconFindingReport   (protocol/recon/finding-report.schema.json)
        |
        v
agentsam_sdk.repository.recon.validate_report(...)
        |
        v
     capable agent         (verifies, edits, git, tests, PR)
```

Hand-picked slices still work too — `build_task_packet()` takes an explicit slice
list directly when you already know exactly which 5 files matter and don't have a
raw hit list to chunk.

## Rules the worker operates under

- **One question, not a subsystem audit.** "Does this file still read
  `workspace_id`?" — not "audit the workflow runtime."
- **≤5 file slices per packet, supplied — never discovered.** The worker doesn't
  run its own `rg`/`ast-grep`/`find`/`ls`; the controller already ran search and
  chunked the results before the worker ever sees anything. "Do not give Qwen rg."
- **≤2 follow-up reads**, each still inside the packet's ceilings.
- **Read-only diagnostics only**, and only ones the controller pre-approved
  (`allowed_diagnostics` in the packet) — `git status`/`diff`/`log`/`show`, a
  syntax check, a single named test. Never `git add|commit|reset|push`, never a
  migration, never a full build or deploy, never `ast-grep --fix`/`sg --update-all`
  on the target files.
- **No branch ownership.** The worker's only output is a `ReconFindingReport`. It
  never calls `write_file` against the repository.
- **Never guess.** If the supplied slices don't answer the question, the worker
  returns `status: "needs_context"` with `reason` and `missing` — not a
  fabricated finding. `validate_report` rejects any `answered` report that cites
  a file outside the packet's slices, so a worker can't paper over a gap with
  invented evidence either.
- **A slice's `kind` (when present) is a controller-verified structural label,
  not a hint the worker should second-guess.** `sql_string` and `member` are not
  the same finding even when the literal text matches.

## Where each half lives

| Half | Module | Notes |
| --- | --- | --- |
| Search adapter | `agentsam_sdk.repository.recon.from_matches` | Read-only; takes raw hits (`{path, line, kind?}` — `rg --json` mapped to this shape works today) and turns them into one or more bounded packets, chunking anything over 5 files. Runs no search itself. |
| Controller (hand-picked packets) | `agentsam_sdk.repository.recon.build_task_packet` | For when you already know the exact ≤5 files/lines — no hit list to chunk. |
| Validator (gate reports) | `agentsam_sdk.repository.recon.validate_report` | Structural check + the "never guess" rule + citation check (findings can't reference files the worker was never given). Raises `ReportError`; callers must discard, not patch, a rejected report. |
| Contracts | `protocol/recon/task-packet.schema.json`, `protocol/recon/finding-report.schema.json` | Provider-neutral; usable from the CLI, the MCP surface, or a Worker. |
| CLI | `python -m agentsam_sdk.repository.recon pack \| validate` | Same `ToolInput`/`ToolResult` contract as every other `agentsam_sdk` tool — read-only by default, gets a receipt. |

This kit intentionally stops at the report. Model orchestration — which model
answers a packet, retries, cost routing, whether delegation happens at all — is
host policy, same as the rest of the SDK's "host integration and ownership"
boundary in the root README. A future `bounded-mutation` contract (a worker
allowed to perform one specific, proven-safe transform, e.g. "rename import path
A → B") is a separate, narrower protocol, not an extension of recon's read-only
contract. `ast-grep` structural classification (splitting hits by node kind) is
also a separate, not-yet-installed layer — `from_matches` accepts a `kind` per
hit today so that classification slots in later without a schema change.

## Example

```python
import json, subprocess
from agentsam_sdk.repository import recon

raw = subprocess.run(
    ["rg", "--json", "-e", "workspace_id", "backend/workflows", "backend/http/workflows"],
    capture_output=True, text=True,
).stdout

matches = [
    {"path": obj["data"]["path"]["text"], "line": obj["data"]["line_number"]}
    for obj in (json.loads(line) for line in raw.splitlines())
    if obj.get("type") == "match"
]

packets = recon.from_matches(
    ".",
    question="Does this file still depend on removed workspace-scoped columns?",
    matches=matches,
    task_id_prefix="workflow-v2-runtime-audit",
)
# 16 files -> 4 packets of <=5 files each, ready to hand to a capable model
# for direct classification, or to a delegated worker later.
```

See [`REPOSITORY_INTELLIGENCE.md`](REPOSITORY_INTELLIGENCE.md) for the git-level
evidence layer (hotspots/churn) that can help decide *which* files to search in
the first place, and [`protocol/README.md`](../protocol/README.md) (rule 6) for
the read-only, no-hardcoded-identity law this module follows.
