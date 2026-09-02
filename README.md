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

### Prerequisite: build the pack

`agentpack` imports a pack; it does not build one. Build it first, from the
RAD toolkit checkout (`rad-agent-toolkit\rad-mcp-server`), with one
`build-pack.ps1` run per transport:

```powershell
# stdio, portable — produces dist\pack_stdio (skills + mcps + runtime + config)
PowerShell -ExecutionPolicy Bypass -File `
  .\rad-mcp-server\scripts\install\pack\build-pack.ps1 `
  -Transports stdio `
  -Portable `
  -Runtime windows-amd64 `
  -NonInteractive

# http — produces dist\pack_http (skills + mcps\http.json only, no runtime)
PowerShell -ExecutionPolicy Bypass -File `
  .\rad-mcp-server\scripts\install\pack\build-pack.ps1 `
  -PackName pack_http `
  -Transports http `
  -HttpUrl "http://127.0.0.1:8080/mcp" `
  -HttpToken $env:RAD_MCP_TOKEN `
  -MarketToken $env:RAD_MARKET_TOKEN `
  -NonInteractive
```

`-PackName` (or `-Out`) controls the output directory; left unset, it
defaults to `dist\pack_stdio` for `-Portable` and `dist\packing` otherwise —
pass `-PackName pack_http` as shown above to get `dist\pack_http` instead.
That output directory is the path the corresponding `agentpack` option below
imports from — `dist\pack_stdio` for Option B, `dist\pack_http` for Option A.

Run these commands from the repository root where you want the `artifacts/`
folder to live. Which import commands you run depends on the MCP transport
the producer built: **HTTP** (four commands) or **stdio with a portable
runtime** (three commands, everything in one import).

### Option A: HTTP

```powershell
# 1. init
agentpack init -n rad-agent-toolkit-http --version 0.25.1

# 2. skills import
agentpack skill import "C:\source-repo\dist\pack_http\skills" -n rad-agent-toolkit-http

# 3. MCPs import
agentpack mcp import "C:\source-repo\dist\pack_http\mcps\http.json" -n rad-agent-toolkit-http

# 4. validate
agentpack validate -n rad-agent-toolkit-http

# 5. pack
agentpack package -n rad-agent-toolkit-http
```

Produces in `artifacts\rad-agent-toolkit-http\dist\packages\`:

```text
claude-desktop-cowork-plugin-0.25.1.plugin
claude-desktop-rad-network-toolkit-http-127.0.0.1-0.25.1.mcpb
claude-code-0.25.1.zip
copilot-0.25.1.zip
codex-marketplace-0.25.1.zip
universal-0.25.1.zip
```

#### Install: Claude Desktop

1. Open Claude Desktop -> **Settings -> Manage plugins -> Add -> Upload
   plugin**.
2. Select `claude-desktop-cowork-plugin-0.25.1.plugin`. This installs all 11
   skills as one plugin.
3. Go to **Settings -> Extensions -> Install extension**.
4. Select `claude-desktop-rad-network-toolkit-http-127.0.0.1-0.25.1.mcpb`.
5. Claude prompts for a bearer token. Enter only the token value — no
   `Bearer ` prefix, AgentPack adds it when calling the server.
6. Fully quit Claude Desktop, including the background/tray process, then
   reopen it so the new plugin and extension load.

The `.mcpb` embeds AgentPack's Windows stdio-to-HTTP bridge. On first use it
installs itself under `%LOCALAPPDATA%\AgentPack\bridge\` — no Python,
Node.js, or source checkout is needed on the installing machine.

#### Install: GitHub Copilot

1. Extract `copilot-0.25.1.zip` to a folder.
2. In VS Code, open **Copilot Settings -> Plugins -> + Install Plugin from
   Source**.
3. Select the extracted folder, then click **Install** on the added plugin.
4. Open the Command Palette (`Ctrl+Shift+P`) and run **Developer: Reload
   Window**.
5. Start a new Copilot session — the skills and the HTTP MCP's tools load
   with the plugin, and the bearer token is embedded already, so nothing else
   is prompted.

#### Install: Codex

1. Extract `codex-marketplace-0.25.1.zip` to a folder.
2. Open **Settings -> Codex Settings -> Plugins -> Add -> + Add a
   marketplace**.
3. Select the extracted folder — it contains `.agents/plugins/marketplace.json`.
4. Install/enable the listed plugin from the Plugins screen.
5. If an older plugin already provides an MCP server with the same name,
   remove it first; otherwise Codex keeps the earlier definition and may use
   the wrong transport or token.
6. Start a new Codex session. The bearer token is embedded in the package, so
   Codex is not prompted for it.

#### Install: Claude Code

1. Add `claude-code-0.25.1.zip` as a local marketplace source (see
   [docs/adapters.md](docs/adapters.md) for the exact steps for your Claude
   Code version).
2. Install/enable the plugin from that marketplace.
3. Start a new session — the skills and the HTTP MCP's tools become
   available. Claude Code does not receive the bearer token; if the server
   requires one, configure it directly in Claude Code's own MCP settings.

### Option B: stdio (portable pack)

Use this when the producer built a *portable* pack for stdio — one that
bundles its own runtime so the installing machine needs nothing preinstalled.
`agentpack pack import` brings in the skills, the stdio MCP definition, and
the runtime/config payload in a single step:

```powershell
# 1. init
agentpack init -n rad-agent-toolkit-stdio --version 0.25.1

# 2. import the whole portable pack (skills + MCP + runtime + config)
agentpack pack import "C:\source-repo\dist\pack_stdio" -n rad-agent-toolkit-stdio

# 3. validate
agentpack validate -n rad-agent-toolkit-stdio

# 4. pack
agentpack package -n rad-agent-toolkit-stdio
```

`pack import` only accepts a directory whose `pack.json` declares
`"portable": true` with a `runtime/` and/or `config/` payload — this is
currently how the RAD toolkit's stdio build works, not http. An HTTP pack has
no runtime to bundle (it's a remote URL), so it always uses Option A, even if
it was produced by the same build script.

Produces in `artifacts\rad-agent-toolkit-stdio\dist\packages\`:

```text
claude-desktop-cowork-plugin-0.25.1.plugin
claude-desktop-rad-network-toolkit-stdio-0.25.1.mcpb
claude-code-0.25.1.zip
copilot-0.25.1.zip
codex-marketplace-0.25.1.zip
universal-0.25.1.zip
```

#### Install: Claude Desktop

1. Open Claude Desktop -> **Settings -> Manage plugins -> Add -> Upload
   plugin**.
2. Select `claude-desktop-cowork-plugin-0.25.1.plugin`. This installs all 11
   skills as one plugin.
3. Go to **Settings -> Extensions -> Install extension**.
4. Select `claude-desktop-rad-network-toolkit-stdio-0.25.1.mcpb`.
5. There is no token prompt: the `.mcpb` already bundles the portable stdio
   runtime, so nothing else installs or downloads on first use.
6. Fully quit Claude Desktop, including the background/tray process, then
   reopen it so the new plugin and extension load.

#### Install: GitHub Copilot

1. Extract `copilot-0.25.1.zip` to a folder.
2. In VS Code, open **Copilot Settings -> Plugins -> + Install Plugin from
   Source**.
3. Select the extracted folder, then click **Install** on the added plugin.
4. Open the Command Palette (`Ctrl+Shift+P`) and run **Developer: Reload
   Window**.
5. Start a new Copilot session — the skills and the stdio MCP's tools load
   with the plugin, launching the bundled runtime directly.

#### Install: Codex

1. Extract `codex-marketplace-0.25.1.zip` to a folder.
2. Open **Settings -> Codex Settings -> Plugins -> Add -> + Add a
   marketplace**.
3. Select the extracted folder — it contains `.agents/plugins/marketplace.json`.
4. Install/enable the listed plugin from the Plugins screen.
5. If an older plugin already provides an MCP server with the same name,
   remove it first; otherwise Codex keeps the earlier definition and may
   launch the wrong runtime.
6. Start a new Codex session.

#### Install: Claude Code

1. Add `claude-code-0.25.1.zip` as a local marketplace source (see
   [docs/adapters.md](docs/adapters.md) for the exact steps for your Claude
   Code version).
2. Install/enable the plugin from that marketplace.
3. Start a new session — the skills and the stdio MCP's tools become
   available, running the bundled portable runtime with no separate install
   step.

## Advanced

Use the same `-n` value with every command within one option — e.g.
`rad-agent-toolkit-http` throughout Option A, `rad-agent-toolkit-stdio`
throughout Option B. Each resolves to its own project under `artifacts/`:

```text
artifacts/
  rad-agent-toolkit-http/
    agentpack.yaml
    skills/
    mcp/
    dist/
  rad-agent-toolkit-stdio/
    agentpack.yaml
    skills/
    mcp/
    portable/
    dist/
```

Change the version later without recreating the project:

```powershell
agentpack version set 0.25.2 -n rad-agent-toolkit-http
agentpack version set 0.25.2 -n rad-agent-toolkit-stdio
```

`package` clears the previous `dist/` output before creating the new build, so
the package directory always reflects the current skills and MCP definitions.

### What to import

#### Skills

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

#### MCP servers

Import a normal MCP JSON file rather than writing another format by hand:

```powershell
# HTTP or stdio are detected from the JSON content, not its filename.
agentpack mcp import "C:\source-repo\dist\pack_http\mcps\http.json" -n rad-agent-toolkit-http

# Replace an already imported server when its source definition changed.
agentpack mcp import "C:\source-repo\dist\pack_http\mcps\http.json" -n rad-agent-toolkit-http --overwrite
```

An MCP JSON may contain `mcpServers`, `servers`, or one bare server entry. A
`command` makes it a stdio MCP; a `url` makes it an HTTP MCP.

If importing would replace files under `artifacts/<name>/mcp/` or `skills/`,
AgentPack asks before overwriting. Use `--overwrite` only when replacing those
imported definitions is intended.

#### Portable packs (stdio only)

```powershell
agentpack pack import "C:\source-repo\dist\pack_stdio" -n rad-agent-toolkit-stdio
```

Expects a directory shaped like:

```text
pack_stdio/
  pack.json               # "portable": true, "runtime": "windows-amd64", ...
  skills/
  mcps/
    stdio.json
  runtime/                # the bundled, self-contained executable
  config/                 # optional mutable configuration template
```

This replaces the separate `skill import` + `mcp import` steps: it copies the
skills, creates the MCP definition, and copies `runtime/`/`config/` into
`artifacts/<name>/portable/`. Generated packages resolve `pack.json`'s
`package_root_placeholder` (default `${packageRoot}`) to wherever the client
installs the package or plugin, so the stdio command can point at the bundled
runtime without knowing the install path in advance.

There is no HTTP equivalent: an HTTP MCP is a remote URL, not a bundled
runtime, so it has nothing for `pack import` to carry beyond what
`skill import` + `mcp import` already handle. Import an HTTP pack with Option
A above, even if it was produced by the same build script as a portable pack.

**Windows path length.** Claude Desktop installs each MCPB under a deeply
nested per-user path (`AppData\Local\Packages\...\Claude Extensions\<name>\`).
If the bundled `runtime/` is a PyInstaller `--onedir` build, its own
third-party package data (e.g. `jsonschema_specifications`'s per-draft
schema files, all of which `jsonschema` imports unconditionally — none of
them can be pruned) nests deep enough that the full path can exceed
Windows' 260-char `MAX_PATH`, causing a `FileNotFoundError` for a file that
genuinely exists. AgentPack keeps the MCPB's own `manifest.json` `name` to
10 characters (see the CHANGELOG) to leave headroom for this, but that only
covers the extension-name segment it controls; the fixed MSIX container
prefix and the runtime's own depth are not adjustable from here. Building
the portable runtime with `--onefile` instead avoids the problem entirely —
it self-extracts to a short `%TEMP%\_MEIxxxxxx` path at run time instead of
living under the long Extensions path. If you can't rebuild, unblock the
current install by setting
`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` (DWORD)
to `1` and rebooting (Windows 10 1607+, requires admin).

### HTTP tokens

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

### Package files reference

Generic name pattern for any package/version, in `dist/packages/`:

| File | Use it for |
|---|---|
| `claude-desktop-cowork-plugin-<version>.plugin` | All skills in Claude Desktop |
| `claude-desktop-<mcp-name>-http-<host>-<version>.mcpb` | The HTTP MCP in Claude Desktop |
| `claude-desktop-<mcp-name>-stdio-<version>.mcpb` | The stdio MCP in Claude Desktop |
| `claude-code-<version>.zip` | Claude Code marketplace |
| `copilot-<version>.zip` | Copilot plugin |
| `codex-marketplace-<version>.zip` | Codex marketplace and plugin |
| `universal-<version>.zip` | Archive/repackaging, not direct installation |

Open `artifacts/<name>/dist/packages/INSTALL.md` after every package command
— it lists the exact files made for your package version.

### Useful commands

```powershell
agentpack init -n NAME --version X.Y.Z
agentpack version set X.Y.Z -n NAME
agentpack skill import PATH -n NAME
agentpack mcp import FILE.json -n NAME
agentpack pack import PORTABLE_PACK_DIRECTORY -n NAME
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

### Project layout

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
  portable/               # imported self-contained runtime/config, when present
    runtime/
    config/
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
