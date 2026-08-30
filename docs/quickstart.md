# AgentPack quick start

Use one package name with every command. AgentPack stores its workspace in
`artifacts/<name>/`; it never imports source material or writes generated
packages anywhere else.

## 1. Create a package and set its version

```powershell
agentpack init -n my-agent --version 1.0.0
```

Change the package version later:

```powershell
agentpack version set 1.0.1 -n my-agent
```

## 2. Import skills and MCP definitions

```powershell
agentpack skill import "C:\source\skills" -n my-agent
agentpack mcp import "C:\source\mcps\stdio.json" -n my-agent
```

Import an HTTP definition in exactly the same way:

```powershell
agentpack mcp import "C:\source\mcps\http.json" -n my-agent
```

For an HTTP MCP, import only its JSON definition. AgentPack generates the
Claude Desktop MCPB and Windows bridge automatically. The bridge installs on
first use under `%LOCALAPPDATA%\AgentPack\bridge`; a producer repository does
not provide an MCPB or a local runtime.

## 3. Package

```powershell
agentpack package -n my-agent --knowledge served
```

Use `--knowledge bundled` when skill `references/` files must travel inside
the client packages. `served` ships the `SKILL.md` files and expects the MCP
to provide the larger knowledge at runtime.

Generated files are under:

```text
artifacts\my-agent\dist\packages\
```

Open `artifacts\my-agent\dist\INSTALL.md` after every package command. It
lists the exact generated filenames and installation instructions.

## Install by client

| Client | Install the generated package |
|---|---|
| Claude Desktop | Upload the `.plugin` in **Settings → Manage plugins → Add → Upload plugin**. Install each `.mcpb` in **Settings → Extensions → Install extension**. For HTTP MCPs, enter the endpoint and requested token/header values; AgentPack installs its bridge under `%LOCALAPPDATA%\AgentPack\bridge` automatically. |
| Claude Code | Add the extracted package as a local marketplace, then install its plugin. |
| GitHub Copilot | Extract the Copilot ZIP. Open Copilot **Settings → Plugins → + Install Plugin from Source**, then choose the extracted folder and click **Install** on its row. Run **Developer: Reload Window** from `Ctrl+Shift+P`; the plugin then loads its skills and MCP configuration. |
| Codex | Extract the Codex marketplace ZIP. Open Codex **Settings → Codex Settings → Plugins → Add → + Add a marketplace**, then install the listed plugin. Adding a marketplace alone does not switch plugins. Use `codex plugin add <plugin>@<marketplace>`; if an old plugin provides the same MCP, first run `codex plugin remove <old-plugin>@<old-marketplace>`. For a bearer-token HTTP MCP, set the Windows user environment variable named in generated `INSTALL.md`, then reopen Codex and start a new chat. |
| Universal | Keep as an interchange/archive package; clients do not install it directly. |
