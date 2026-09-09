# AgentSam Recon Protocol (aka "MiniCodeScout")

Provider-neutral contracts for delegating bounded read-only investigation to a cheap or
local model (Ollama/Qwen-class, mini-tier hosted models, etc.) without giving it branch,
Git, or write authority. See [docs/RECON.md](../../docs/RECON.md) for the design rationale
and current status — the delegation step itself is currently benched in favor of plain
deterministic search; these contracts are the reusable substrate for when it isn't.

`task-packet.schema.json` is the only input a recon worker receives. It is built by a
deterministic controller (`repository.intelligence`, `rg`, AST lookups) — never by the
worker itself, and never contains a workspace/tenant ID as the task handle.

`finding-report.schema.json` is the only output a recon worker may return. A worker that
cannot answer from its supplied slices must return `status: "needs_context"`, not a guess.

These schemas intentionally do not define a code-mutation contract. Recon workers observe;
they do not write, `git commit`, migrate, or merge. A future `bounded-mutation` protocol
(scoped to specific, proven-safe transforms) is a separate contract, not an extension of
this one — see ownership rule 6 in `protocol/README.md`.
