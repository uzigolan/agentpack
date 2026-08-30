# AgentPack

[![CI](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml/badge.svg)](https://github.com/uzigolan/agentpack/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Package Agent Skills and MCP servers once, then install the resulting packages
in Claude Desktop, GitHub Copilot, or Codex.

AgentPack keeps each package project in `artifacts/<name>/`. Skills, MCP
definitions, builds, and distributable packages stay there. Nothing is written
into a client's configuration folders.

## How to work

Run these five commands from the repository root where you want the
`artifacts/` folder to live:

```powershell
# 1. init
agentpack init -n rad-agent-toolkit --version 0.25.1

# 2. skills import
agentpack skill import "C:\source-repo\dist\packing\skills" -n rad-agent-toolkit

# 3. MCPs import
agentpack mcp import "C:\source-repo\dist\packing\mcps\http.json" -n rad-agent-toolkit

# 4. validate
agentpack validate -n rad-agent-toolkit

# 5. pack
agentpack package -n rad-agent-toolkit
```

Use the same `-n rad-agent-toolkit` with every command. It resolves:

```text
artifacts/
  rad-agent-toolkit/
    agentpack.yaml
    skills/
    mcp/
    dist/
```

Change the version later without recreating the project:

```powershell
agentpack version set 0.25.2 -n rad-agent-toolkit
```

`package` clears the previous `dist/` output before creating the new build, so
the package directory always reflects the current skills and MCP definitions.

## What to import

### Skills

Import either a folder containing many skill folders, a single skill folder, or
a ZIP. Each skill needs a `SKILL.md`; `references/` is optional.

```text
skills/
  network-analysis/
    SKILL.md
    references/            # optional
  incident-report/
    SKILL.md
```

All imported skills are copied into `artifacts/<name>/skills/`. AgentPack never
uses the source skill directory as package output.

### MCP servers

Import a normal MCP JSON file rather than writing another format by hand:

```powershell
# HTTP or stdio are detected from the JSON content, not its filename.
agentpack mcp import "C:\source-repo\dist\packing\mcps\http.json" -n rad-agent-toolkit

# Replace an already imported server when its source definition changed.
agentpack mcp import "C:\source-repo\dist\packing\mcps\http.json" -n rad-agent-toolkit --overwrite
```

An MCP JSON may contain `mcpServers`, `servers`, or one bare server entry. A
`command` makes it a stdio MCP; a `url` makes it an HTTP MCP.

If importing would replace files under `artifacts/<name>/mcp/` or `skills/`,
AgentPack asks before overwriting. Use `--overwrite` only when replacing those
imported definitions is intended.

## HTTP tokens

For an HTTP MCP such as:

```json
{
  "mcpServers": {
    "rad-network-toolkit": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
```

AgentPack keeps the actual header value in the artifact MCP definition.

- Copilot and Codex packages embed that header automatically. Their users are
  not prompted for it.
- Claude Desktop does not embed it. Its MCPB asks the installer for the token;
  the user enters the token only and AgentPack adds `Bearer `.
- Claude Code and the universal archive do not receive the stored value.

Treat `artifacts/<name>/` and the Copilot/Codex packages as secret material.
They are ignored by Git by default; do not share them or force-add them to a
repository.

## Result: `rad-agent-toolkit-http`

This is what AgentPack created for the existing
`rad-agent-toolkit-http` example after running:

```powershell
agentpack package -n rad-agent-toolkit-http
```

```text
artifacts/
  rad-agent-toolkit-http/
    agentpack.yaml                         # package name, version, targets
    skills/                                # 11 imported skill folders
      rad-core/SKILL.md
      rad-cli-operations/SKILL.md
      ...
    mcp/
      rad-network-toolkit.yaml             # imported HTTP MCP definition
    dist/                                  # deleted and recreated by package
      INSTALL.md                           # exact install instructions
      agentpack-build.json                 # build and SHA256 record
      build/                               # unpacked output; inspect only
        claude-desktop/
        claude-code/
        copilot/
        codex/
        universal/
      packages/                            # the files to install or distribute
        claude-desktop-cowork-plugin-0.25.11.plugin
        claude-desktop-rad-network-toolkit-http-127.0.0.1-0.25.11.mcpb
        claude-code-0.25.11.zip
        copilot-0.25.11.zip
        codex-marketplace-0.25.11.zip
        universal-0.25.11.zip
```

The important result is `dist/packages/`:

| File | Use it for |
|---|---|
| `claude-desktop-cowork-plugin-<version>.plugin` | All skills in Claude Desktop |
| `claude-desktop-<mcp-name>-http-<host>-<version>.mcpb` | The HTTP MCP in Claude Desktop |
| `claude-desktop-<mcp-name>-stdio-<version>.mcpb` | A stdio MCP in Claude Desktop |
| `claude-code-<version>.zip` | Claude Code marketplace |
| `copilot-<version>.zip` | Copilot plugin |
| `codex-marketplace-<version>.zip` | Codex marketplace and plugin |
| `universal-<version>.zip` | Archive/repackaging, not direct installation |

Open `artifacts/<name>/dist/INSTALL.md` after every package command. It lists
the exact files made for your package version and installation instructions.

## Install a package

### Claude Desktop

1. For skills: **Settings -> Manage plugins -> Add -> Upload plugin**. Select
   the `.plugin` file.
2. For every MCP: **Settings -> Extensions -> Install extension**. Select its
   `.mcpb` file.
3. For HTTP MCPBs, Claude prompts for the token. Enter only the token, without
   `Bearer `.
4. Fully quit Claude Desktop, including the tray process, then reopen it.

For an HTTP MCP, the MCPB includes AgentPack's Windows stdio-to-HTTP bridge.
On first use it installs under:

```text
C:\Users\<user>\AppData\Local\AgentPack\bridge\
```

No Python, Node.js, source checkout, or separate producer-provided MCPB is
needed on the installing machine.

### GitHub Copilot

1. Extract `copilot-<version>.zip`.
2. Open Copilot **Settings -> Plugins -> + Install Plugin from Source**.
3. Select the extracted folder, then click **Install** on the added plugin.
4. In VS Code, run **Developer: Reload Window** from `Ctrl+Shift+P`.
5. Start a new Copilot session. The skills and MCP tools load with the plugin.

### Codex

1. Extract `codex-marketplace-<version>.zip`.
2. Open **Settings -> Codex Settings -> Plugins -> Add -> + Add a marketplace**.
3. Select the extracted folder. It contains `.agents/plugins/marketplace.json`.
4. Install/enable the listed plugin in the Plugins screen.
5. Start a new Codex session.

If an older plugin provides the same MCP server name, remove it first. Codex
otherwise keeps the earlier server definition and may appear to use the wrong
transport or token.

### Claude Code and Universal

`claude-code-<version>.zip` is a Claude Code local marketplace package. The
universal ZIP is an archive/repackaging format; it is not installed directly by
a client.

## Useful commands

```powershell
agentpack init -n NAME --version X.Y.Z
agentpack version set X.Y.Z -n NAME
agentpack skill import PATH -n NAME
agentpack mcp import FILE.json -n NAME
agentpack validate -n NAME
agentpack package -n NAME
agentpack package -n NAME -t copilot       # build just one target
agentpack package -n NAME -t codex
agentpack clean -n NAME                    # removes only artifacts/NAME/dist
agentpack list-targets -v
agentpack doctor -n NAME
```

Use `--knowledge bundled` when a skill's `references/` directory must travel
inside packages. `served` (the default) ships `SKILL.md` and expects a connected
MCP server to provide larger reference material at runtime.

## Project layout

Each artifact project is self-contained:

```text
artifacts/<name>/
  agentpack.yaml
  skills/
    <skill-name>/
      SKILL.md
      references/          # optional
  mcp/
    <server-name>.yaml
  dist/                    # generated and replaced on every package run
```

`agentpack.yaml` is the only required top-level definition. The imported
skills and MCP YAML files are its local, package-owned inputs.

## More documentation

- [INSTALL.md](INSTALL.md): install the `agentpack` command itself
- [docs/quickstart.md](docs/quickstart.md): concise command reference
- [docs/mcp-schema.md](docs/mcp-schema.md): MCP YAML schema
- [docs/adapters.md](docs/adapters.md): target-specific behavior
- [docs/manifest.md](docs/manifest.md): every `agentpack.yaml` field
- [examples/network-operations](examples/network-operations): sample package

Licensed under [Apache-2.0](LICENSE).
