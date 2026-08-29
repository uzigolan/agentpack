# Target adapters

**Contents:** [Definition of supported](#definition-of-supported) ·
[claude-desktop](#claude-desktop) · [claude-code](#claude-code) ·
[copilot-vscode](#copilot-vscode) · [copilot-intellij](#copilot-intellij) ·
[codex](#codex) · [universal](#universal) · [Writing an adapter](#writing-an-adapter)

## Definition of supported

A target is only `plugin` / `bundle` grade when this whole chain exists:

```text
canonical source → AgentPack → portable artifact → client-supported import
```

If the only integration is "copy this config file by hand", the artifact type is
`configuration-export`. That distinction is deliberate and is printed in the
build summary and in every generated README.

Two rules hold for every adapter:

1. **AgentPack never writes into a client's configuration directory.** It writes
   into `dist/` only; installation happens through the client's own UI or import
   command.
2. **Skills are never installed one by one.** They travel inside the target's
   package (plugin, bundle or overlay archive), so a package is installed and
   removed as one unit.

| Target | Artifact type | Import path |
|---|---|---|
| `claude-desktop` | bundle | Settings → Extensions → Install from file |
| `claude-code` | plugin | `/plugin marketplace add` or `~/.claude/plugins/` |
| `copilot-vscode` | configuration-export | merge `mcp.json`, copy workspace tree |
| `copilot-intellij` | configuration-export (experimental) | merge `mcp.json` |
| `codex` | configuration-export | append TOML tables |
| `universal` | archive | AgentPack itself |

---

## claude-desktop

Emits one MCPB bundle per MCP server, plus a single skills plugin.

```text
dist/build/claude-desktop/
├── mcpb/<server>/manifest.json
├── plugin/<pkg>/.claude-plugin/plugin.json
├── plugin/<pkg>/skills/<name>/
└── README.md

dist/packages/
├── <pkg>-claude-desktop-<server>-<version>.mcpb
└── <pkg>-claude-desktop-skills-<version>.zip
```

All of them install through **Settings → Extensions → Install from file**.

Key facts encoded in the adapter:

- `manifest_version` is `"0.3"`; `server.type` is `node`, `python` or `binary`,
  inferred from the executable.
- `user_config` entries are prompted at import time — this is the only target
  with a native secret prompt for MCP configuration. Values are referenced as
  `${user_config.<key>}`; `${__dirname}` resolves to the extracted bundle.
- A `.mcpb` file is a plain ZIP of the bundle directory. `agentpack package`
  produces one per server because **a bundle declares exactly one server**.
- Skills ship as one plugin package, not as folders to drop into
  `~/.claude/skills/`.
- Absolute paths in `user_config.default` are machine-specific. Do not assume a
  bundle built on one machine works on another without re-pointing them.
- Remote (`http`/`sse`) servers are bridged with `npx -y mcp-remote <url>`, with
  each declared header appended as `--header "Name: ${user_config.x}"`. Claude
  Desktop can only launch local processes, so this is the only way an HTTP MCP
  server reaches it. The installing machine needs Node.js.

## claude-code

Emits a plugin directory plus a local marketplace manifest.

```text
dist/build/claude-code/
├── <pkg>/.claude-plugin/plugin.json
├── <pkg>/.mcp.json          # root key: mcpServers
├── <pkg>/skills/<name>/
├── <pkg>/{commands,agents,hooks}/
└── .claude-plugin/marketplace.json
```

There is no install-time secret prompt, so `source: user` values become `<KEY>`
placeholders and are listed in the generated README.

## copilot-vscode

```text
dist/build/copilot-vscode/
├── mcp.json                        # fragment for the user-level config
├── workspace/.vscode/mcp.json      # drop into a repo root
├── workspace/.github/skills/<name>/
├── workspace/.github/prompts/
└── README.md
```

- Root key is `servers`. Using Claude's `mcpServers` here fails silently — this
  is the single most common cross-client mistake.
- Secrets go through `inputs[]` with `${input:<id>}` and `password: true`, so VS
  Code prompts and stores them; AgentPack writes nothing sensitive.
- There is no plugin container, so the package is a **workspace overlay**: unzip
  `workspace/` over your own repository. It lands in your repo, never in a VS
  Code or Copilot configuration directory.
- User-level config paths (only if you want the servers everywhere):
  `%APPDATA%\Code\User\mcp.json`,
  `~/Library/Application Support/Code/User/mcp.json`, `~/.config/Code/User/mcp.json`.

## copilot-intellij

Same JSON dialect, different location
(`%LOCALAPPDATA%\github-copilot\intellij\mcp.json` /
`~/.config/github-copilot/intellij/mcp.json`), no workspace-level override.
Marked **experimental**: verify skill discovery against your plugin version.

## codex

```text
dist/build/codex/
├── config.toml       # [mcp_servers.<name>] tables
├── skills/<name>/
└── README.md
```

- Configuration is **TOML**, not JSON. `type = "local"` for stdio servers.
- Environment goes in a nested `[mcp_servers.<name>.env]` table.
- Remote servers require the experimental streamable-HTTP client, and tokens are
  referenced via `bearer_token_env_var` rather than written to the file.
- Codex has no plugin or extension container. The whole target is one archive
  applied in a single step; `skills/` is extracted as a unit into
  `~/.agents/skills/`, never skill by skill.

## universal

Loss-free interchange format: `plugin.json` index + verbatim `skills/`, `mcp/`,
`prompts/`, `agents/`, `commands/`, `hooks/`, `assets/`. No client consumes it
directly; keep it for archival, diffing and re-packaging.

## Writing an adapter

```python
class MyClientAdapter(TargetAdapter):
    name = "my-client"

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(skills=Support.FULL, mcp_stdio=Support.FULL, ...)

    def validate(self, package: AgentPackage) -> Diagnostics:
        ...   # target-specific warnings, with stable codes

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        self.stage_skills(package, output_dir / "skills")
        write_json(output_dir / "config.json", ...)
        write_text(output_dir / "README.md", self.readme(package, steps))
        return BuildResult(target=self.name, output_dir=output_dir,
                           artifact_type=ArtifactType.CONFIG_EXPORT)
```

Archive naming is handled by the builder:
`<package>-<target>-<version>.zip` for the whole target directory, or
`<package>-<target>-<label>-<version><suffix>` for each `ArchiveSpec` an adapter
returns. Every artifact therefore names its target and version.

Before writing one, answer the research checklist in
[compatibility.md](compatibility.md) and record the answers there.
