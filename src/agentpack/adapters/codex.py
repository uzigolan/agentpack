"""OpenAI Codex adapter — installable plugin directory."""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.adapters.claude_code import mcp_server_entry
from agentpack.core.diagnostics import AP2201, Diagnostics
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArchiveSpec,
    ArtifactType,
    BuildResult,
    Support,
    TargetCapabilities,
)


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(toml_string(v) for v in values) + "]"


class CodexAdapter(TargetAdapter):
    name = "codex"
    adapter_version = 1

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            skills=Support.FULL,
            mcp_stdio=Support.FULL,
            mcp_http=Support.PARTIAL,
            user_config=Support.PARTIAL,
            prompts=Support.PARTIAL,
            agents=Support.NONE,
            commands=Support.NONE,
            hooks=Support.NONE,
            artifact_type=ArtifactType.PLUGIN,
            notes=(
                "A self-contained Codex plugin: install its folder from Codex's Plugins "
                "screen. It includes both Agent Skills and its MCP server declarations."
            ),
        )

    def validate(self, package: AgentPackage) -> Diagnostics:
        diags = Diagnostics()
        for server in package.mcp_servers:
            if server.is_remote:
                diags.warning(
                    AP2201,
                    f"'{server.name}': remote transport requires Codex's experimental "
                    "RMCP client to be enabled",
                    target=self.name,
                )
        return diags

    def _config_toml(self, package: AgentPackage) -> str:
        lines = [
            f"# {package.metadata.title} {package.metadata.version}",
            "# Merge these tables into ~/.codex/config.toml",
        ]
        for server in package.mcp_servers:
            lines += ["", f"[mcp_servers.{server.name}]"]
            if server.is_remote and server.endpoint:
                lines.append(f"url = {toml_string(server.endpoint.url)}")
                if any(var.secret for var in server.headers.values()):
                    lines.append(
                        f"bearer_token_env_var = {toml_string(f'{server.name.upper()}_TOKEN')}"
                    )
            else:
                assert server.command is not None
                lines.append('type = "local"')
                lines.append(f"command = {toml_string(server.command.executable)}")
                if server.command.args:
                    lines.append(f"args = {toml_array(list(server.command.args))}")
                if server.command.cwd:
                    lines.append(f"cwd = {toml_string(server.command.cwd)}")

            env = self.mcp_env_literals(server)
            env.update(
                {k: self.placeholder(k, v) for k, v in sorted(server.environment.items())
                 if v.source.value == "user"}
            )
            if env:
                lines += ["", f"[mcp_servers.{server.name}.env]"]
                lines += [f"{k} = {toml_string(v)}" for k, v in sorted(env.items())]
        return "\n".join(lines)

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        meta = package.metadata
        # Codex requires the plugin root directory and manifest name to match.
        plugin_name = meta.name.lower().replace("_", "-").replace(".", "-")
        plugin_dir = output_dir / "plugins" / plugin_name
        description = meta.description or f"{meta.title} skills and MCP tools."
        manifest = {
            "name": plugin_name,
            "version": meta.version,
            "description": description,
            "author": {"name": meta.author_name},
            "skills": "./skills/",
            "interface": {
                "displayName": meta.title,
                "shortDescription": description[:128],
                "longDescription": description,
                "developerName": meta.author_name,
                "category": "Productivity",
                "capabilities": [],
                "defaultPrompt": f"Use the {meta.title} skills and MCP tools.",
            },
        }
        if package.mcp_servers:
            manifest["mcpServers"] = "./.mcp.json"
            write_json(
                plugin_dir / ".mcp.json",
                {"mcpServers": {
                    server.name: mcp_server_entry(self, server) for server in package.mcp_servers
                }},
            )
        if meta.keywords:
            manifest["keywords"] = meta.keywords
        if meta.homepage:
            manifest["homepage"] = meta.homepage
        if meta.repository:
            manifest["repository"] = meta.repository
        if meta.license:
            manifest["license"] = meta.license

        write_json(plugin_dir / ".codex-plugin" / "plugin.json", manifest)
        self.stage_skills(package, plugin_dir / "skills")
        write_text(plugin_dir / "README.md", self.readme(package))
        # Codex discovers a marketplace manifest at this exact path within
        # the selected source directory (not at the source root).
        write_json(
            output_dir / ".agents" / "plugins" / "marketplace.json",
            {
                "name": f"{plugin_name}-marketplace",
                "interface": {"displayName": f"{meta.title} Marketplace"},
                "plugins": [
                    {
                        "name": plugin_name,
                        "source": {"source": "local", "path": f"./plugins/{plugin_name}"},
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            },
        )
        write_text(output_dir / "README.md", self.readme(package))
        return BuildResult(
            target=self.name,
            output_dir=output_dir,
            artifact_type=ArtifactType.PLUGIN,
            archive_specs=[ArchiveSpec(root=".", label="marketplace")],
        )

    def install_steps(self, package: AgentPackage) -> list[str]:  # noqa: ARG002
        plugin_name = package.metadata.name.lower().replace("_", "-").replace(".", "-")
        return [
            "1. Extract `"
            f"{package.metadata.name}-codex-marketplace-{package.metadata.version}.zip` from "
            "`dist/packages/` into a folder.",
            "2. Click Codex's **Settings** gear, then choose **Codex Settings** to open the "
            "Settings UI.",
            "3. Open **Plugins → Add → + Add a marketplace** and select the extracted folder "
            "(it contains `.agents/plugins/marketplace.json`).",
            f"4. Find `{plugin_name}` in the Plugins list and choose **Install**.",
            "The plugin contains its skills and MCP server configuration; start a new thread "
            "after installation.",
        ]
