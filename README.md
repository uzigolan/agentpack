# AgentPack

[![CI](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml/badge.svg)](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Author AI agent capabilities **once** — Agent Skills and MCP servers — then build
packages for Claude Desktop, Claude Code, Copilot and Codex.

AgentPack never writes into `~/.claude`, `~/.codex` or your VS Code profile, and
skills are never installed one by one. It produces packages you version, publish
and import through each client's own UI.

**Contents:** [Setup](#setup) · [How to work](#how-to-work) · [Editing the manifest](#editing-the-manifest) ·
[Your repo layout](#your-repo-layout) ·
[Writing a skill](#writing-a-skill) · [Writing an MCP definition](#writing-an-mcp-definition) ·
[What you get](#what-you-get) · [Combining repos](#combining-repos) ·
[Everyday commands](#everyday-commands) · [Options](#options) · [Docs](#docs)

Full install instructions: [INSTALL.md](INSTALL.md)

For the short command workflow, see [Quick start](docs/quickstart.md).

---

## Setup

The quickest install — isolated, and on your PATH permanently:

```powershell
pipx install git+https://github.com/uzigolan/agentpack.git
agentpack version
```

Prefer a virtual environment, or working from a clone? See
[INSTALL.md](INSTALL.md) for all three options, plus verification and
troubleshooting.

---

## How to work

Three steps. That's the whole tool.

> Run these **in your capability repo** — the one holding your skills and MCP
> definitions — not inside the AgentPack repo.

```powershell
cd path\to\my-capabilities-repo

# 1. create a self-contained package workspace
#    -> artifacts/netops-skills/ (manifest, imported inputs, and dist/ output)
agentpack init -n netops-skills --version 1.0.0

# 2. import what you ship into that workspace
agentpack skill import C:\source-repo\skills -n netops-skills
agentpack mcp add netops -n netops-skills --command python --arg -m --arg netops_mcp.server --secret NETOPS_TOKEN

# 3. check and build
agentpack validate -n netops-skills
agentpack package -n netops-skills
```

Without a directory argument, `init` creates `artifacts/<package-name>/` and puts
only `agentpack.yaml`, `.gitignore` and `README.md` there. It does not invent
`skills/` or `mcp/` directories — `skill import` creates the local skills copy,
and `--example` creates a working sample.

Afterwards, pass `-n <package-name>` to the working commands (`skill`, `mcp`,
`validate`, `build`, `package`, `inspect`, `clean`, or `doctor`). It resolves
`artifacts/<package-name>/agentpack.yaml` automatically; use `-f` only for a
manifest outside the standard workspace.

Set the package version later with:

```powershell
agentpack version set 1.1.0 -n netops-skills
```

All generated artifacts go into one folder, `dist/` by default. Choose another
at init time, and it is written into the manifest and `.gitignore`:

```powershell
agentpack init -n netops-skills -o artifacts
```

Every command also takes `-f` to point at a specific manifest, with any
filename, from anywhere:

```powershell
agentpack validate -f D:\repos\netops\netops.agentpack.yaml
agentpack package  -f D:\repos\netops\netops.agentpack.yaml
```

Paths inside the manifest (`skills:`, `mcp:`, `include:`, `build.output`) always
resolve relative to **the manifest's own directory**, never to your current
directory — so the artifact folder lands next to the manifest.

---

## Editing the manifest

You can write `agentpack.yaml` by hand, or let AgentPack maintain it. Edits are
round-tripped, so your comments and formatting survive.

```powershell
# skills - registering the same path twice is a no-op
agentpack skill add skills/network-analysis
agentpack skill remove skills/network-analysis     # unregisters; files stay

# MCP servers
agentpack mcp add netops --command python --arg -m --arg netops_mcp.server ‹
                        --secret NETOPS_TOKEN --env NETOPS_READONLY=true
agentpack mcp add monitoring -t http -u https://mcp.example.com/mcp --header Authorization
agentpack mcp update netops -d "Read-only device access" --remove-env NETOPS_READONLY
agentpack mcp remove monitoring
```

`skill add` already covered by a parent entry (`skills:`) reports it and changes
nothing. `mcp add` creates `mcp/<name>.yaml` and registers the directory once.

### Importing MCP servers from JSON

Already have the server configured in a client? Import it instead of retyping:

```powershell
agentpack mcp import "$env:APPDATA\Code\User\mcp.json"        # VS Code Copilot
agentpack mcp import claude_desktop_config.json               # Claude
agentpack mcp import manifest.json                            # an MCPB bundle
agentpack mcp import mcp.json --server netops                 # just one server
agentpack mcp import mcp.json --update                        # merge into existing
agentpack mcp import mcp.json --overwrite                     # replace existing definitions
```

Recognised shapes: `mcpServers`, `servers` (with `inputs`), an MCPB
`manifest.json`, or a bare server object (needs `--name`).

**Secrets are never carried over.** A `${input:x}` / `${user_config.x}` /
`<KEY>` placeholder becomes `source: user`, using the client's own metadata for
the description and whether it is a password. A real credential sitting in the
JSON is also converted to `source: user, secret: true` — the value is dropped.

Then open `dist/INSTALL.md` — it lists every artifact that was produced, which
client each one is for, the exact install steps and the values the user must
supply.

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
├── mcp/
│   ├── netops.yaml         ← stdio server
│   └── monitoring.yaml     ← http server
└── dist/                   ← generated; every artifact lands here
```

Minimal `agentpack.yaml`:

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage

metadata:
  name: netops-skills
  version: 1.0.0
  description: Network operations skills and MCP servers.

targets: [claude-desktop, claude-code, copilot, codex, universal]

skills:
  - path: skills/     # every nested SKILL.md folder and every .zip skill is picked up
mcp:
  - path: mcp/        # every *.yaml is picked up
```

Point `skills:` / `mcp:` at whatever folders you already use — a directory of
many, or a single skill directory / single file. A registered skills directory
may mix ordinary skill folders and `.zip` files. Each ZIP may contain one skill
or a whole skills collection; AgentPack finds every `SKILL.md` and emits the
same unpacked `<skill-name>/SKILL.md` layout, with `references/` included only
in `bundled` knowledge mode.

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
dist/                                    # or whatever you set as the output folder
├── INSTALL.md                           # start here: every artifact + how to install it
├── agentpack-build.json                 # targets, artifact types, sha256 each
├── build/                               # unpacked, for inspection and diffing
│   ├── claude-desktop/mcpb/<server>/    # one bundle per MCP server
│   ├── claude-desktop/cowork-plugin/<pkg>/ # all skills as one Cowork plugin
│   ├── claude-code/<pkg>/               # plugin dir + .mcp.json + skills/
│   ├── copilot/.copilot-plugin/          # host-neutral Copilot plugin manifest
│   ├── codex/config.toml + skills/
│   └── universal/                       # loss-free archive
└── packages/                            # what you actually distribute
    ├── netops-skills-claude-desktop-netops-1.0.0.mcpb
    ├── netops-skills-claude-desktop-monitoring-1.0.0.mcpb
    ├── netops-skills-claude-desktop-cowork-plugin-1.0.0.plugin
    ├── netops-skills-claude-code-1.0.0.zip
    ├── netops-skills-copilot-1.0.0.zip
    └── netops-skills-codex-1.0.0.zip
```

`dist/INSTALL.md` is generated on every build and is what you hand to whoever
installs the package: it names each file, which client it is for, the steps, and
the values they must supply. Each `dist/build/<client>/README.md` has the same
detail for one client only.

Every archive is named `<package>-<target>[-<part>]-<version>`, so a file is
never ambiguous about which client and which version it belongs to.

Per client — all of these are package installs, nothing is copied by hand:

| Client | How it is installed |
|---|---|
| Claude Desktop | Settings → Extensions → **Install from file** → each `.mcpb`, then the `.plugin` Cowork skills package |
| Claude Code | `/plugin marketplace add <dist/build/claude-code>` then `/plugin install <name>` — servers and skills arrive together |
| GitHub Copilot | Use the Copilot plugin-management UI in VS Code or IntelliJ to add the package folder or ZIP |
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
targets: [claude-desktop, copilot]

include:
  - path: ../repo-a                    # a directory containing agentpack.yaml
  - path: ../repo-b/agentpack.yaml     # or the manifest itself
```

Duplicate skill or server names across repos fail the build (`AP1004`), which is
what you want when merging catalogs.

---

## Everyday commands

```powershell
agentpack init -n NAME [-o FOLDER]      # manifest only; --example adds a sample
agentpack skill add PATH                # register a skill path (idempotent)
agentpack mcp add NAME ...              # create and register an MCP definition
agentpack mcp import FILE.json          # import from a client's JSON config
agentpack validate                      # is my project correct?
agentpack build                         # unpacked directories in <output>/build/
agentpack package                       # + distributable archives in <output>/packages/
agentpack build --target claude-desktop # just one client
agentpack build -o somewhere-else       # override the artifact folder for one run
agentpack validate -f path\to\my.yaml   # use a specific manifest, any filename
agentpack inspect                       # what the adapters actually see
agentpack list-targets -v               # clients + capability matrix
agentpack doctor                        # environment + project health
agentpack clean                         # remove the artifact folder
```

Without `-f`, AgentPack searches the current directory and its parents for an
`agentpack.yaml`. `-p <dir>` starts that search somewhere else.

---

## Options

**Skill knowledge** — where a skill's `references/` corpus lives:

```powershell
agentpack build                        # served (default)
agentpack build --knowledge bundled    # ships inside the skill; works offline
```

In `served` mode `references/` is stripped from the artifact and an MCP server
is expected to provide it at runtime, which keeps skill packages small and the
corpus centrally updatable. Served artifacts get a `<!--agentpack-mode:served-->`
stamp so a runtime check can tell which mode is installed. Use `bundled` when
the skill must work with no MCP connection.

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

- [INSTALL.md](INSTALL.md) — install, verify, upgrade, troubleshoot
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, checks, adding an adapter, project rules
- [SECURITY.md](SECURITY.md) — threat model and reporting
- [CHANGELOG.md](CHANGELOG.md)
- Licensed under [Apache-2.0](LICENSE)
