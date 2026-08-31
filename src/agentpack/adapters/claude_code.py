"""Claude Code adapter — plugin directory with a marketplace entry.

Encoded facts:
- A plugin is a directory containing ``.claude-plugin/plugin.json``.
- Skills live in ``skills/<name>/SKILL.md``; commands in ``commands/``;
  agents in ``agents/``; hooks in ``hooks/``.
- MCP servers are declared in ``.mcp.json`` using the ``mcpServers`` root key
  (note: *not* ``servers`` — that is the VS Code Copilot spelling).
- ``.claude-plugin/marketplace.json`` lets the directory be added as a local
  marketplace with ``/plugin marketplace add <path>``.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArtifactType,
    BuildResult,
    MCPServer,
    Support,
    TargetCapabilities,
)


def mcp_server_entry(
    adapter: TargetAdapter,
    server: MCPServer,
    package: AgentPackage | None = None,
    package_root: str = "${CLAUDE_PLUGIN_ROOT}",
) -> dict:
    """`mcpServers` value in Claude's JSON dialect."""
    env = adapter.mcp_env_literals(server)
    env.update({k: adapter.placeholder(k, v) for k, v in sorted(server.user_inputs().items())
                if k in server.environment})
    if server.is_remote and server.endpoint:
        entry: dict = {"type": server.transport.value, "url": server.endpoint.url}
        headers = {
            k: adapter.placeholder(k, v) for k, v in sorted(server.headers.items())
        }
        if headers:
            entry["headers"] = headers
        return entry

    assert server.command is not None
    resolve = (
        (lambda value: adapter.package_path(package, value, package_root))
        if package is not None
        else (lambda value: value)
    )
    entry = {
        "type": "stdio",
        "command": resolve(server.command.executable),
        "args": [resolve(arg) for arg in server.command.args],
    }
    if server.command.cwd:
        entry["cwd"] = resolve(server.command.cwd)
    if env:
        entry["env"] = env
    return entry


class ClaudeCodeAdapter(TargetAdapter):
    name = "claude-code"
    adapter_version = 1

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            skills=Support.FULL,
            mcp_stdio=Support.FULL,
            mcp_http=Support.FULL,
            user_config=Support.NONE,
            prompts=Support.FULL,
            agents=Support.FULL,
            commands=Support.FULL,
            hooks=Support.FULL,
            artifact_type=ArtifactType.PLUGIN,
            notes=(
                "Claude Code has no install-time prompt for secrets. Values marked "
                "`source: user` are written as `<KEY>` placeholders in `.mcp.json` and "
                "must be edited (or supplied via the environment) after install."
            ),
        )

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        meta = package.metadata
        plugin_dir = output_dir / meta.name

        plugin_json = {
            "name": meta.name,
            "description": meta.description,
            "version": meta.version,
        }
        if meta.authors:
            plugin_json["author"] = {"name": meta.author_name}
        if meta.homepage:
            plugin_json["homepage"] = meta.homepage
        if meta.repository:
            plugin_json["repository"] = meta.repository
        if meta.license:
            plugin_json["license"] = meta.license
        if meta.keywords:
            plugin_json["keywords"] = meta.keywords
        write_json(plugin_dir / ".claude-plugin" / "plugin.json", plugin_json)

        if package.mcp_servers:
            write_json(
                plugin_dir / ".mcp.json",
                {"mcpServers": {
                    s.name: mcp_server_entry(self, s, package) for s in package.mcp_servers
                }},
            )

        self.stage_portable_payload(package, plugin_dir)
        self.stage_skills(package, plugin_dir / "skills")
        for assets, folder in (
            (package.commands, "commands"),
            (package.agents, "agents"),
            (package.hooks, "hooks"),
        ):
            for asset in assets:
                dest = plugin_dir / folder / asset.relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(asset.source.read_bytes())

        for asset in package.assets:
            dest = plugin_dir / "assets" / asset.relative_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(asset.source.read_bytes())

        write_json(
            output_dir / ".claude-plugin" / "marketplace.json",
            {
                "name": f"{meta.name}-marketplace",
                "owner": {"name": meta.author_name},
                "plugins": [
                    {
                        "name": meta.name,
                        "source": f"./{meta.name}",
                        "description": meta.description,
                        "version": meta.version,
                    }
                ],
            },
        )

        write_text(output_dir / "README.md", self.readme(package))
        return BuildResult(
            target=self.name, output_dir=output_dir, artifact_type=ArtifactType.PLUGIN
        )

    def install_steps(self, package: AgentPackage) -> list[str]:
        return [
            "Add this directory as a local marketplace, then install the plugin. "
            "The plugin carries the MCP servers and every skill, so nothing is copied "
            "into `~/.claude/` by hand:",
            "",
            "```bash",
            "/plugin marketplace add <absolute path to this directory>",
            f"/plugin install {package.metadata.name}@{package.metadata.name}-marketplace",
            "```",
            "",
            "Then edit the plugin's `.mcp.json` and replace every `<KEY>` placeholder, "
            "or export the values in your environment before starting Claude Code.",
        ]


# Re-exported for adapters that share Claude's JSON dialect.
__all__ = ["ClaudeCodeAdapter", "mcp_server_entry"]
