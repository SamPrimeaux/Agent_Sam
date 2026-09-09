#!/usr/bin/env node

import pkg from '../package.json' with { type: 'json' };
import readline from 'readline';
import path from 'node:path';
import { buildLocalScaffoldMeta, LANE_KEYS, RUN_TARGETS } from './lib/local-scaffold.js';
import { writeScaffoldFiles } from './lib/write-files.js';
import { initializeGitRepository } from './lib/init-git.js';
import { initializeLocalSqlite } from './local/sqlite.js';
import { printContextSummary } from './lib/detect-context.js';
import { promptOptionalByokKeys } from './lib/prompt-byok.js';
import { runStartLocal } from './commands/start-local.js';
import { runTunnel } from './commands/tunnel.js';
import { runDeploy } from './commands/deploy.js';
import { runIdentityPreview } from './commands/identity-preview.js';
import { runIdentityInit } from './commands/identity-init.js';
import { runContext } from './commands/context.js';
import { runDb } from './commands/db.js';
import { runStatus } from './commands/status.js';
import { runTui } from './commands/tui.js';
import { runDockerize } from './commands/dockerize.js';
import { runMini } from './commands/mini.js';
import { runMerkle } from './commands/merkle.js';
import { runDeployReceipt } from './commands/deploy-receipt.js';
import { runSecurity } from './commands/security.js';
import { runRecon } from './commands/recon.js';
import { SLASH_COMMANDS, SHELL_PHASES } from './lib/slash-commands.js';
import fs from 'node:fs';
import { repositoryRoot } from './knowledge/config.js';

const VERSION = pkg.version;

function createPrompt() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return {
    ask: (q) => new Promise((resolve) => rl.question(q, resolve)),
    close: () => rl.close(),
  };
}

function printHelp() {
  console.log(`
  Agent Sam SDK — CLI v${VERSION}

  Usage:
    agentsam context [--json]  Git repo/revision + bridge configuration from any repo
    agentsam init              Configure knowledge in this repo; --name scaffolds a new project
    agentsam index             Plan/run incremental AST and optional embeddings (--help)
    agentsam search "query"    Retrieve indexed code/text; --semantic enables embeddings
    agentsam repo snapshot     Git composition/churn; --save retains observations
    agentsam mini <name>       Create and preview a small local gadget (--help for options)
    agentsam merkle            File integrity, snapshots, comparisons, and TUI (--help)
    agentsam deploy-receipt    Merkle deploy/checkpoint capture + promote/failure receipts (--help)
    agentsam recon             Bounded-worker task packets + finding-report validation (--help)
    agentsam security          Dependency scan, log triage, and verified repair (--help)
    agentsam status [--json]   Live local Git + DB + API + PTY status
    agentsam db init|status    Manage the project-local SQLite database
    agentsam tui               Zero-dependency ANSI Agent Sam dashboard
    agentsam tui rich          Optional Python Rich dashboard (--install for local venv)
    agentsam start-local       Local PTY on ws://127.0.0.1:3099 (no tunnel, no Cloudflare)
    agentsam shell             Terminal commands + presentation catalog
    agentsam tunnel            Explicitly expose local PTY when remote access is wanted
    agentsam deploy            Graduate to Cloudflare / GCP when ready
    agentsam dockerize         Build/run app, knowledge, or CAD containers (--help)
    agentsam identity preview  Local auth portal preview
    agentsam identity init     Add reusable identity package surfaces
    agentsam --version
    agentsam --help

  Context options:
    --json                     Machine-readable output
    --cwd <path>               Resolve a different working directory
    --remote <name>            Preferred Git remote (default origin; falls back to first remote)

  Init is completable with Node only — no IAM login, no OAuth, no Cloudflare.
  Prove locally first; deploy prompts for accounts only when you choose to ship.

  Tunnel options:
    --quick                    Quick tunnel (default) — trycloudflare.com URL
    --named                    Named CF tunnel (needs --tunnel-name --hostname --zone-id)
    --port <n>                 Local PTY port (default 3099)
    --token <sdk_…>            Use existing AGENTSAM_SDK_TOKEN (skip browser auth)

  Init options:
    --name <name>              Project directory name
    --lane <fullstack|cms|data|crm|creative>
    --run-target <local|cloudflare|gcp>   Default: local
    --yes                      Skip confirmation
  `);
}

function parseInitArgs(argv) {
  const opts = {
    projectName: '',
    lane: 'fullstack',
    runTarget: 'local',
    yes: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--yes' || arg === '-y') opts.yes = true;
    else if (arg === '--name') opts.projectName = argv[++i] || '';
    else if (arg === '--lane') opts.lane = argv[++i] || 'fullstack';
    else if (arg === '--run-target' || arg === '--target') opts.runTarget = argv[++i] || 'local';
  }
  return opts;
}

function parseDeployArgs(argv) {
  const opts = { target: '', accountId: '' };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--target') opts.target = argv[++i] || '';
    else if (arg === '--account-id') opts.accountId = argv[++i] || '';
  }
  return opts;
}

async function runLocalInit(config) {
  const { projectName, lane, runTarget, prompt } = config;

  const meta = buildLocalScaffoldMeta(
    { projectName, lane, runTarget },
    VERSION,
  );

  console.log(`
  ┌──────────────────────────────────────┐
  │  Agent Sam — local-first scaffold   │
  ├──────────────────────────────────────┤
  │  Name:     ${meta.projectName.padEnd(25)}│
  │  Lane:     ${meta.laneKey.padEnd(25)}│
  │  Run:      ${meta.runTarget.padEnd(25)}│
  └──────────────────────────────────────┘
  `);

  const dir = writeScaffoldFiles(meta.projectName, meta.files);
  const git = initializeGitRepository(dir);
  const db = await initializeLocalSqlite({
    dbPath: path.join(dir, '.agentsam', 'data', 'agentsam.sqlite'),
    schemaPath: path.join(dir, 'db', 'schema.sql'),
  });

  console.log(`
  ✓ Project      ${dir}
  ${git.ok ? '✓' : '⚠'} Git          ${git.ok ? 'initialized' : 'git not found; initialize it when available'}
  ✓ Environment  ${path.join(dir, '.env')}
  ✓ SQLite       ${db.dbPath} (${db.tables.length} tables)
  ✓ Local API    Node · http://127.0.0.1:8787
  ✓ Terminal UI  ANSI built in · Rich optional

  Next:`);
  console.log(`    cd ${meta.projectName}`);
  for (const step of meta.next_steps) {
    console.log(`    ${step}`);
  }

  if (prompt && process.env.AGENTSAM_SDK_TOKEN) {
    console.log('\n  Optional — BYOK keys for IAM dashboard Agent Sam (skip with Enter):\n');
    await promptOptionalByokKeys(process.env.AGENTSAM_SDK_TOKEN, prompt);
  }

  console.log(`
  Local means local: no Worker, tunnel, IAM login, or cloud database is required.
  `);
}

async function initInteractive(partial = {}) {
  const prompt = createPrompt();

  console.log(`
  ╔════════════════════════════════╗
  ║   Agent Sam SDK — Init            ║
  ║   Local-first · Node only         ║
  ╚════════════════════════════════╝
  `);

  const projectName =
    partial.projectName ||
    (await prompt.ask('  1) Project name: '));

  if (!partial.lane) {
    console.log(`
  2) Lane:
    1) Full Stack   2) CMS   3) Data   4) CRM   5) Creative
  `);
  }
  const laneKey = partial.lane
    ? partial.lane
    : LANE_KEYS[await prompt.ask('  Pick lane [1-5]: ')] || 'fullstack';

  if (!partial.runTarget) {
    console.log(`
  3) Future deploy target?

    1) Local only / decide later
    2) Cloudflare later (Worker + D1 adapter at deploy time)
    3) GCP later (your Google Cloud project)
  `);
  }
  const runTarget = partial.runTarget
    ? partial.runTarget
    : RUN_TARGETS[await prompt.ask('  Select [1]: ')] || 'local';

  // Credential detection is demand-driven, not unconditional. missingForInit()
  // already knows local needs nothing (`if (runTarget === 'local') return []`)
  // — it just never got consulted before this fix, because detectContext()
  // used to run before runTarget was even known. runTarget alone is enough
  // to decide whether detection is needed at all, so skip the subprocess
  // calls entirely for local instead of just hiding their output.
  if (runTarget !== 'local') {
    const { detectContext, missingForInit } = await import('./lib/detect-context.js');
    const ctx = await detectContext();
    if (missingForInit(ctx, process.env.AGENTSAM_SDK_TOKEN || '', { runTarget }).length) {
      printContextSummary(ctx);
    }
  }

  await runLocalInit({ projectName, lane: laneKey, runTarget, prompt });
  prompt.close();
}

async function initFromArgs(argv) {
  const opts = parseInitArgs(argv);
  if (!opts.projectName) {
    console.error('\n  ✗ --name is required for non-interactive init.\n');
    process.exit(1);
  }
  await runLocalInit({ ...opts, prompt: null });
}

async function runShellInfo(argv = []) {
  const sub = argv[0] || 'list';
  if (sub === 'demo' || sub === 'ansi') {
    await runTui(['ansi', ...argv.slice(1)]);
    return;
  }
  if (sub === 'rich') {
    await runTui(['rich', ...argv.slice(1)]);
    return;
  }
  if (sub !== 'list' && sub !== 'status') {
    throw new Error(`unknown shell command: ${sub}`);
  }

  const next = SHELL_PHASES.find((p) => p.status === 'next' || p.status === 'current');
  console.log(`
  ╔═══════════════════════════════╗
  ║        Agent Sam Terminal         ║
  ╚════════════════════════════════╝

  Local PTY   agentsam start-local     ws://127.0.0.1:3099
  ANSI TUI    agentsam tui             zero-dependency Node UI
  Rich TUI    agentsam tui rich        optional richer Python UI
              agentsam tui rich --install
  DB          agentsam db status       local SQLite

  Current milestone: ${next?.label ?? 'local terminal experience'}

  Slash commands (${SLASH_COMMANDS.length} registered):
`);
  for (const row of SLASH_COMMANDS) {
    console.log(`    ${row.cmd.padEnd(14)} ${row.description}`);
  }
}

const command = process.argv[2];
const rest = process.argv.slice(3);

if (command === '--version' || command === '-v') {
  console.log(VERSION);
} else if (command === '--help' || command === '-h' || !command) {
  printHelp();
} else if (command === 'context') {
  try {
    await runContext(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'status') {
  try {
    await runStatus(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'db') {
  try {
    await runDb(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'tui') {
  try {
    await runTui(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'shell') {
  try {
    await runShellInfo(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'start-local') {
  await runStartLocal({});
} else if (command === 'tunnel') {
  try {
    await runTunnel(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'deploy') {
  try {
    await runDeploy(parseDeployArgs(rest));
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'dockerize') {
  try {
    await runDockerize(rest);
  } catch (e) {
    console.error(`\n  ✗ ${e?.message || e}\n`);
    process.exit(1);
  }
} else if (command === 'security' || command === 'sca') {
  await runSecurity(rest);
} else if (command === 'merkle') {
  await runMerkle(rest);
} else if (command === 'deploy-receipt') {
  await runDeployReceipt(rest);
} else if (command === 'recon') {
  await runRecon(rest);
} else if (command === 'mini') {
  try {
    await runMini(rest);
  } catch (e) {
    console.error(`\n  ${e?.message || e}\n`);
    process.exitCode = 1;
  }
} else if (['index', 'search', 'repo'].includes(command)) {
  try {
    const commands = await import('./commands/knowledge.js');
    await ({ index: commands.runKnowledge, search: commands.runSearch, repo: commands.runRepository })[command](rest);
  } catch (e) { console.error(e.message); process.exitCode = 1; }
} else if (command === 'init') {
  try {
    const existing = !rest.includes('--name') && (rest.includes('.') || rest.includes('--existing') || rest.includes('--cwd') || fs.existsSync(path.join(repositoryRoot(), '.git')));
    if (existing) await (await import('./commands/knowledge.js')).runRepositoryInit(rest);
    else if (rest.includes('--help') || rest.includes('-h')) printHelp();
    else if (rest.some((a) => a.startsWith('--'))) await initFromArgs(rest);
    else await initInteractive({});
  } catch (e) { console.error(e.message); process.exitCode = 1; }
} else if (command === 'identity') {
  const sub = rest[0];
  if (sub === 'preview') {
    try {
      await runIdentityPreview(rest.slice(1));
    } catch (e) {
      console.error(`\n  ✗ ${e?.message || e}\n`);
      process.exit(1);
    }
  } else if (sub === 'init') {
    try {
      await runIdentityInit(rest);
    } catch (e) {
      console.error(`\n  ✗ ${e?.message || e}\n`);
      process.exit(1);
    }
  } else {
    console.error('\n  Usage:\n    agentsam identity preview [--open] [--port 8791]\n    agentsam identity init --name <project> [--brand "Name"]\n');
    process.exit(1);
  }
} else {
  console.error(`\n  Unknown command: ${command}\n`);
  printHelp();
  process.exit(1);
}
