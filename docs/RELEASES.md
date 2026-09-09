# `@inneranimalmedia/agentsam-sdk` release receipts

**2.1.0 is published on npm and is the `latest` dist-tag.** The private identity workspace
continues to ship through the root SDK exports and is not published separately.

| npm version | Published (UTC) | IAM git SHA (40) | Notes |
|-------------|-----------------|------------------|-------|
| 2.1.0 | 2026-09-09 (UTC, approx) | `a2570afdf1ae99542565fa3937abd7dbf95d121f` | Recon bounded-worker protocol: `protocol/recon/*` schemas, `python/agentsam_sdk/repository/recon` (packet/validate + `from_ripgrep`/`from_ast_grep` adapters), `agentsam recon pack\|validate` CLI (#27, #28). SDK-native change — no corresponding IAM platform-repo mirror SHA. |
| 2.0.0 | 2026-09-03T02:21:44.857Z | `ed629869e701809d2bf4c61bd56d05d8d8d1e183` | Stable SDK 2.0.0; npm `latest`; identity bundled through root exports; release verification and dependency scan passed before publish. |
| 2.0.0-alpha.identity.5 | _(pending npm)_ | `df064114eb7f8888f163e4a07dfddf19035b7169` | Password reset service, `registerFinalizeInboundOAuth`, IAM live proof. |
| 2.0.0-alpha.identity.4 | 2026-08-22 | `df064114eb7f8888f163e4a07dfddf19035b7169` | IAM auth portal sync: signup→`/api/auth/signup`, `company-branding.js`, preview stubs. SDK git `d7498ca`. |
| 2.0.0-alpha.identity.3 | 2026-08-22 | `559bc37267f76790136004f5fa94a2bb3cd6a721` | `company` table + `GET/PATCH /api/company` branding SSOT. |
| 2.0.0-alpha.identity.2 | 2026-08-22 | `559bc37267f76790136004f5fa94a2bb3cd6a721` | `agentsam identity init` scaffold; SDK git `029eebf72c8c166e157dd188340ec966755b4735`. |
| 2.0.0-alpha.identity.1 | 2026-08-22 | `559bc37267f76790136004f5fa94a2bb3cd6a721` | Preview CLI + docs/export fixes; SDK git `360a3049bcfdc71f86d795019817a417048abb9a`. |
| 1.9.0 | 2026-08-05T07:12:21.726Z | `fc1628505cb3c9946c149e4c468c2e264d6f381e` | `python/agentsam_sdk/repository/inspect.py` (`--dupes`); CLI `agentsam repository inspect` |
| 1.8.0 | 2026-08-02T13:57:12.080Z | `580547301e370b77ec26bd72558979d335feedd9` | `python/` + `protocol/` in npm `files`; `repository.scan_bloat`; shell-kit folded to `packages/agentsam-shell-kit` (private). SDK git at publish: `ac52669b89ddb16fad87c42fe53f2c93ef13bd1a`. |
| 1.7.0 | 2026-07-14 | _(pre-receipt)_ | Prior publish |

**Pairing (identity alpha .2):** `iam@559bc37267f76790136004f5fa94a2bb3cd6a721` ↔ `@inneranimalmedia/agentsam-sdk@2.0.0-alpha.identity.2`

**Pairing (identity alpha .1):** `iam@559bc37267f76790136004f5fa94a2bb3cd6a721` ↔ `@inneranimalmedia/agentsam-sdk@2.0.0-alpha.identity.1`

**Pairing (identity alpha):** `iam@559bc37267f76790136004f5fa94a2bb3cd6a721` ↔ `@inneranimalmedia/agentsam-sdk@2.0.0-alpha.identity`

**Pairing (1.9):** `iam@fc1628505cb3c9946c149e4c468c2e264d6f381e` ↔ `@inneranimalmedia/agentsam-sdk@1.9.0`
