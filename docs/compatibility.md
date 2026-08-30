# Compatibility

Client formats move faster than this project. Everything here must be
re-verified against official documentation before it is relied on.

**Contents:** [Matrix](#capability-matrix) · [Research checklist](#adapter-research-checklist) ·
[Cross-client gotchas](#cross-client-gotchas) · [Keeping it honest](#keeping-it-honest)

## Capability matrix

Generated live by `agentpack list-targets -v`. Snapshot:

| Target | skills | stdio | http | user-config | prompts | agents | commands | hooks |
|---|---|---|---|---|---|---|---|---|
| claude-desktop | ✅ | ✅ | ✅ Windows bridge | ✅ | ⚠ | ❌ | ❌ | ❌ |
| claude-code | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| copilot-vscode | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠ | ⚠ | ❌ |
| copilot-intellij | ✅ | ✅ | ✅ | ✅ | ⚠ | ❌ | ❌ | ❌ |
| codex | ✅ | ✅ | ⚠ experimental | ❌ | ⚠ | ❌ | ❌ | ❌ |
| universal | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

`user-config` means the client can prompt the user for a secret at install time.
Where it is ❌, AgentPack emits placeholders and documents them instead —
diagnostic `AP2501`.

## Adapter research checklist

Answer before implementing or bumping an adapter:

```text
[ ] Official plugin/package format?
[ ] Publicly documented? JSON Schema available?
[ ] Can skills be packaged? Multiple per package?
[ ] Can MCP servers be packaged? Multiple per package?
[ ] Can MCP user configuration / secrets be declared?
[ ] Is there a package manifest? An archive format?
[ ] Can users install through the UI, or only by editing config?
[ ] Update / versioning support?
[ ] Hooks, agents, commands, prompts?
[ ] Naming restrictions? File size limits?
[ ] Signing required? Marketplace required?
[ ] Official validator?
[ ] Minimum client version?
```

## Cross-client gotchas

Hard-won, each one has cost someone a debugging session:

1. **MCP root key differs.** `servers` (VS Code / JetBrains Copilot) vs
   `mcpServers` (Claude) vs `[mcp_servers.<n>]` (Codex, TOML). Wrong key = silent
   no-op, not an error.
2. **Codex is TOML.** Every other target here is JSON.
3. **MCPB paths are absolute** and baked in at build time. A bundle is
   machine-specific until the `user_config` defaults are re-pointed.
4. **One MCPB = one server.** Multi-server packages produce multiple bundles.
5. **"Fully quit" means fully quit.** Claude Desktop keeps running in the system
   tray; closing the window does not reload extensions.
6. **Secrets have no universal home.** MCPB prompts, VS Code prompts, Claude Code
   and Codex do not. Never assume the artifact can carry them.
7. **Skill directory name is the identity.** Frontmatter `name` that disagrees
   with the directory breaks discovery on at least one client, so AgentPack
   rejects it at load time (`AP1005`).
8. **Skill copies drift.** The moment a skill exists in more than one place
   (repo, user dir, zipped artifact), you need an automated equality check. This
   is what the build manifest's per-target SHA-256 is for.
9. **Tool count matters.** Clients degrade when a package registers a very large
   number of tools. Prefer several small, profile-gated MCP servers over one
   server exposing everything.
10. **Read-only deployments are a real target.** Shipping the same package with
    write tools removed is a deployment decision; model it explicitly rather
    than forking the package.
11. **Per-skill installation does not scale.** Anything installed file by file
    drifts, cannot be uninstalled cleanly and cannot be versioned. Skills ship
    inside the target's package or not at all.

## Keeping it honest

Each adapter carries metadata (`adapter_version`, `spec_version`,
`last_verified`, `notes`) surfaced by `agentpack list-targets -v` and recorded in
`dist/agentpack-build.json`. Golden tests in `tests/` pin the generated shape so
a format change is a visible diff rather than a silent breakage.
