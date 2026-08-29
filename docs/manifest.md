# `agentpack.yaml`

One manifest per producing repository. A repo that ships skills and MCP
definitions owns its own `agentpack.yaml`; nothing else re-lists its contents.

The file may have any name. Commands find it in one of two ways:

```powershell
agentpack validate                       # search the CWD and its parents
agentpack validate -p path\to\repo       # search there instead
agentpack validate -f path\to\my.yaml    # use exactly this file
```

Every path inside the manifest resolves relative to **the manifest's own
directory**, which becomes the project root — never relative to your current
directory. `build.output` follows the same rule, so `dist/` is written next to
the manifest.

**Contents:** [Example](#example) · [Fields](#fields) · [Skills](#skills) ·
[Composing repos](#composing-repos) · [Overrides](#target-overrides)

## Example

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage

metadata:
  name: network-operations          # slug: [A-Za-z0-9-_.]
  displayName: Network Operations Toolkit
  version: 0.1.0
  description: Skills and MCP integrations for network operations.
  license: Apache-2.0
  homepage: https://example.com
  repository: https://github.com/example/network-operations
  keywords: [network, ops]
  authors:
    - name: Example Team

targets: [universal, claude-desktop, claude-code, copilot, codex]

include: []                       # other AgentPack projects, by reference
skills:
  - path: skills/                   # folders and/or .zip skill packages, or one skill directory
mcp:
  - path: mcp/                      # a directory of *.yaml, or one file
prompts: []
instructions: []
agents: []
commands: []
hooks: []
assets: []

build:
  output: dist
  clean: true
  reproducible: true
  knowledge: served                 # served | bundled

compatibility:
  unsupportedFeaturePolicy: warn    # ignore | warn | error

targetOptions:
  copilot:
    category: developer-tools

targetRaw:                          # escape hatch; use sparingly
  claude-desktop: {}
```

## Fields

| Field | Required | Notes |
|---|---|---|
| `apiVersion` | yes | Mismatch is a warning (`AP1001`), not a failure |
| `kind` | no | Must be `AgentPackage` if present |
| `metadata.name` | yes | Used for artifact and bundle names |
| `metadata.version` | no | Defaults to `0.1.0`; propagated to every target that supports versions |
| `targets` | no | Default set built when `--target` is omitted |
| `include` | no | Paths to other AgentPack projects (see below) |
| `build.knowledge` | no | `served` (default) or `bundled`. Overridable at build time with `--knowledge` |
| `build.output` | no | Folder every generated artifact goes into; defaults to `dist`. Set it with `agentpack init -o <folder>`, or override one run with `agentpack build -o <folder>`. Resolved relative to the manifest. |
| `compatibility.unsupportedFeaturePolicy` | no | `error` promotes compatibility warnings to failures |

## Skills

Each generated skill is a directory:

```text
skills/network-analysis/
├── SKILL.md          # required
├── references/       # stripped in `served` knowledge mode, which is the default
├── scripts/
└── assets/
```

`SKILL.md` frontmatter contract (enforced by the loader):

| Key | Required | Rule |
|---|---|---|
| `name` | yes | Must equal the directory name — every client resolves by directory |
| `description` | yes | Non-empty; clients use it to decide when to load the skill |
| `version` | no | Warned if not `MAJOR.MINOR.PATCH` |

Any other keys are preserved verbatim. AgentPack never rewrites skill content
except to append the served-mode stamp.

## Composing repos

Every producing repo stays self-contained and buildable on its own:

```text
repo-a/agentpack.yaml    skills/  mcp/
repo-b/agentpack.yaml    skills/  mcp/
```

```bash
cd repo-a && agentpack package      # repo-a ships its own artifacts
```

A catalog that redistributes several repos references their manifests rather
than their contents:

```yaml
# catalog/agentpack.yaml
metadata:
  name: catalog
  version: 2.0.0
targets: [claude-desktop, copilot]

include:
  - path: ../repo-a                    # directory containing agentpack.yaml
  - path: ../repo-b/agentpack.yaml     # or the manifest itself
```

Rules:

- Skills, MCP servers, prompts, agents, commands, hooks and assets are merged in.
- The parent owns `metadata`, `targets`, `build` and `compatibility`; a child's
  values are ignored, so each repo can pick different targets for its own builds.
- Duplicate skill or MCP names across repos are errors (`AP1004`) — exactly what
  you want when merging catalogs.
- Circular and missing includes are errors (`AP1007`).
- Includes may point at sibling checkouts outside the project root; that emits an
  informational `AP1007`. Everything a child contributes is still constrained to
  that child's own root.

## Target overrides

Resolution order: canonical model → generic mapping → `targetOptions` →
`targetRaw`. Overrides exist so one client quirk does not force you to duplicate
an entire target manifest.
