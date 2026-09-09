import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const PYTHON_ROOT = fileURLToPath(new URL('../../python', import.meta.url));

export function printReconHelp() {
  console.log(`
  agentsam recon — bounded-worker task packets and finding-report validation

  pack --repo-root <path> --question "..." --slice <path[:start-end]> [--slice ...]
                               Build a bounded ReconTaskPacket (<=5 slices, hard ceilings)
  validate --packet <file> --report <file>
                               Validate a ReconFindingReport against its packet

  pack options:
    --repo-root <path>         Default: .
    --question <text>          Required. Exactly one bounded question.
    --slice <path[:start-end]> Repeatable, up to 5. e.g. --slice src/foo.js:10-40
    --task-id <id>             Default: generated
    --out <file>                Write the packet JSON to a file instead of stdout

  validate options:
    --packet <file>             Required. Path to a packet JSON file.
    --report <file>              Required. Path to a worker's report JSON file.

  Neither command calls a model or writes into the target repository. This is a thin
  passthrough to the bundled Python module (agentsam_sdk.repository.recon) — same
  engine as \`python -m agentsam_sdk.repository.recon\`. See docs/RECON.md.

  Examples:
    agentsam recon pack --repo-root . --question "Does this still read workspace_id?" \\
      --slice backend/workflows/repository.js:1-180 --out /tmp/packet.json
    agentsam recon validate --packet /tmp/packet.json --report /tmp/report.json

  For a raw rg/ast-grep hit list instead of hand-picked slices, use
  agentsam_sdk.repository.recon.{from_ripgrep,from_ast_grep,from_matches}() from
  Python directly — those have no Node CLI surface yet since hit shapes vary by tool.
`);
}

function run(command, args) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      cwd: process.cwd(),
      env: { ...process.env, PYTHONPATH: [PYTHON_ROOT, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter) },
    });
    child.once('error', (err) => {
      console.error(`\n  ✗ Could not run Python (${err.message}). Python 3.10+ must be on PATH for \`agentsam recon\`.\n`);
      resolve(1);
    });
    child.once('exit', (code, signal) => {
      if (signal) { console.error(`\n  ✗ recon ${signal}\n`); resolve(1); }
      else resolve(code ?? 1);
    });
  });
}

export async function runRecon(argv = []) {
  if (!argv.length || argv.includes('--help') || argv.includes('-h')) { printReconHelp(); return; }
  const [command] = argv;
  if (!['pack', 'validate'].includes(command)) {
    console.error(`\n  ✗ Unknown recon command: ${command}. Use \`agentsam recon --help\`.\n`);
    process.exitCode = 2;
    return;
  }
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const code = await run(python, ['-B', '-m', 'agentsam_sdk.repository.recon', ...argv]);
  if (code !== 0) process.exitCode = code;
}
