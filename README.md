# AgentPack

[![CI](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml/badge.svg)](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Author AI agent capabilities **once** — Agent Skills and MCP servers — then build
packages for Claude Desktop, Claude Code, Copilot and Codex.

AgentPack never writes into `~/.claude`, `~/.codex` or your VS Code profile, and
skills are never installed one by one. It produces packages you version, publish
and import through each client's own UI.

**Contents:** [Setup](#setup) · [How to work](#how-to-work) · [Your repo layout](#your-repo-layout) ·
[Writing a skill](#writing-a-skill) · [Writing an MCP definition](#writing-an-mcp-definition) ·
[What you get](#what-you-get) · [Combining repos](#combining-repos) ·
[Everyday commands](#everyday-commands) · [Options](#options) · [Docs](#docs)

---

## Setup

Once, from the repo root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

That installs the `agentpack` command into the venv. Everything below assumes it
is on your PATH; otherwise call `.\.venv\Scripts\agentpack.exe`.

---

## How to work

Three steps. That's the whole tool.

```powershell
# 1. add one file to the repo that produces your skills and MCP servers
agentpack init            # writes agentpack.yaml (skip if you write it by hand)

# 2. check it
agentpack validate

# 3. build installable artifacts
agentpack package
```

Then open `dist/build/<client>/README.md` — it contains the exact install steps
and the list of values the user must supply for that client.

**One `agentpack.yaml` per repo.** Each repo that produces capabilities owns its
own manifest and builds on its own. Nothing central lists what a repo contains.

---

## Your repo layout

You almost certainly already have this. Add only `agentpack.yaml`:

```text
my-capabilities-repo/
├── agentpack.yaml          ← the one file AgentPack needs
├── skills/
│   ├── network-analysis/
│   │   ├── SKILL.md
│   │   └── references/     ← optional; skills without it work the same
│   └── incident-report/
│       └── SKILL.md
└── mcp/
    ├── netops.yaml         ← stdio server
    └── monitoring.yaml     ← http server
```

Minimal `agentpack.yaml`:

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage

metadata:
  name: netops-skills
  version: 1.0.0
  description: Network operations skills and MCP servers.

targets: [claude-desktop, claude-code, copilot-vscode, codex, universal]

skills:
  - path: skills/     # every subdirectory containing a SKILL.md is picked up
mcp:
  - path: mcp/        # every *.yaml is picked up
```

Point `skills:` / `mcp:` at whatever folders you already use — a directory of
many, or a single skill directory / single file.

---

## Writing a skill

A directory with a `SKILL.md`. Three frontmatter rules:

```markdown
---
name: network-analysis      # must equal the directory name
description: >-             # required; clients use it to decide when to load
  Analyse device interface, alarm and health output.
version: 1.0.0              # optional, MAJOR.MINOR.PATCH
---

# Network Analysis

Steps the agent should follow…
```

Everything else in the directory (`references/`, `scripts/`, assets) is copied
verbatim. AgentPack never rewrites your content.

---

## Writing an MCP definition

One YAML file per server. Write it once in AgentPack's neutral form; each client
gets its own dialect.

**stdio:**

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer
metadata:
  name: netops
transport:
  type: stdio
command:
  executable: python
  args: ["-m", "netops_mcp.server"]
environment:
  NETOPS_TOKEN:
    source: user        # the installing user supplies it
    required: true
    secret: true        # never embedded in any artifact
```

**http:**

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer
metadata:
  name: monitoring
transport:
  type: http
endpoint:
  url: https://mcp.example.com/mcp
headers:
  Authorization:
    source: user
    required: true
    secret: true
```

Secrets are declared, never stored. Each client gets the closest native
mechanism: an install-time prompt (Claude Desktop, VS Code) or a documented
`<KEY>` placeholder (Claude Code, Codex).

---

## What you get

```text
dist/
├── agentpack-build.json                 # targets, artifact types, sha256 each
├── build/                               # unpacked, for inspection and diffing
│   ├── claude-desktop/mcpb/<server>/    # one bundle per MCP server
│   ├── claude-desktop/plugin/<pkg>/     # all skills as one plugin
│   ├── claude-code/<pkg>/               # plugin dir + .mcp.json + skills/
│   ├── copilot-vscode/workspace/        # overlay for your own repo
│   ├── codex/config.toml + skills/
│   └── universal/                       # loss-free archive
└── packages/                            # what you actually distribute
    ├── netops-skills-claude-desktop-netops-1.0.0.mcpb
    ├── netops-skills-claude-desktop-monitoring-1.0.0.mcpb
    ├── netops-skills-claude-desktop-skills-1.0.0.zip
    ├── netops-skills-claude-code-1.0.0.zip
    ├── netops-skills-copilot-vscode-1.0.0.zip
    └── netops-skills-codex-1.0.0.zip
```

Every archive is named `<package>-<target>[-<part>]-<version>`, so a file is
never ambiguous about which client and which version it belongs to.

Per client — all of these are package installs, nothing is copied by hand:

| Client | How it is installed |
|---|---|
| Claude Desktop | Settings → Extensions → **Install from file** → each `.mcpb`, then the `-skills-` package the same way |
| Claude Code | `/plugin marketplace add <dist/build/claude-code>` then `/plugin install <name>` — servers and skills arrive together |
| Copilot (VS Code) | unzip the workspace overlay over **your own repo**; optionally merge `mcp.json` into your user config |
| Copilot (JetBrains) | unzip the project overlay; merge `mcp.json` via Settings → Copilot → MCP → Configure |
| Codex | no plugin container: append `config.toml`, extract `skills/` as one unit |

**HTTP MCP + Claude Desktop** is handled for you: Claude Desktop can only launch
local processes, so AgentPack wires the bundle through `npx -y mcp-remote <url>`
and turns your declared headers into install-time prompts. The user needs
Node.js; nothing else.

---

## Combining repos

Only if you want a combined catalog. It references each repo's own manifest —
it never re-lists their contents:

```yaml
# catalog/agentpack.yaml
metadata: { name: catalog, version: 2.0.0 }
targets: [claude-desktop, copilot-vscode]

include:
  - path: ../repo-a                    # a directory containing agentpack.yaml
  - path: ../repo-b/agentpack.yaml     # or the manifest itself
```

Duplicate skill or server names across repos fail the build (`AP1004`), which is
what you want when merging catalogs.

---

## Everyday commands

```powershell
agentpack validate                      # is my project correct?
agentpack build                         # unpacked directories in dist/build/
agentpack package                       # + distributable archives in dist/packages/
agentpack build --target claude-desktop # just one client
agentpack inspect                       # what the adapters actually see
agentpack list-targets -v               # clients + capability matrix
agentpack doctor                        # environment + project health
agentpack clean                         # remove dist/
```

---

## Options

**Skill knowledge** — where a skill's `references/` corpus lives:

```powershell
agentpack build --knowledge bundled    # ships inside the skill; works offline
agentpack build --knowledge served     # stripped; an MCP server serves it
```

Served artifacts get a `<!--agentpack-mode:served-->` stamp so a runtime check
can tell which mode is installed.

**Strict builds** — any warning fails the build:

```powershell
agentpack build --strict
```

**Diagnostics** — stable codes so CI and agents can key off them:

```text
WARNING AP2201 [codex]: 'monitoring': remote transport requires the experimental RMCP client
```

---

## Docs

- [docs/manifest.md](docs/manifest.md) — every `agentpack.yaml` field
- [docs/mcp-schema.md](docs/mcp-schema.md) — MCP definition + how each client maps it
- [docs/adapters.md](docs/adapters.md) — per-client artifact details
- [docs/compatibility.md](docs/compatibility.md) — capability matrix + cross-client gotchas
- [docs/architecture.md](docs/architecture.md) — pipeline, determinism, security
- [examples/network-operations](examples/network-operations) — a complete package
- [AGENTPACK_BASELINE.md](AGENTPACK_BASELINE.md) — original design baseline

## Project

- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, checks, adding an adapter, project rules
- [SECURITY.md](SECURITY.md) — threat model and reporting
- [CHANGELOG.md](CHANGELOG.md)
- Licensed under [Apache-2.0](LICENSE)
