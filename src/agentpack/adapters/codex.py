"""OpenAI Codex adapter — installable plugin directory."""

from __future__ import annotations

import re
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


def bearer_token_env_name(server_name: str) -> str:
    """Return a portable user-environment variable name for a server token."""
    return f"{re.sub(r'[^A-Za-z0-9_]', '_', server_name).upper()}_TOKEN"


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
                if (authorization := server.headers.get("Authorization")) and authorization.secret:
                    if authorization.source.value == "literal" and authorization.value:
                        lines += ["", f"[mcp_servers.{server.name}.http_headers]"]
                        lines.append(f"Authorization = {toml_string(authorization.value)}")
                    else:
                        env_name = bearer_token_env_name(server.name)
                        lines.append(f"bearer_token_env_var = {toml_string(env_name)}")
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

    def _plugin_mcp_entry(self, package, server):  # noqa: ANN001
        """Emit Codex's bearer-token reference instead of a secret placeholder."""
        authorization = server.headers.get("Authorization")
        embedded_bearer_token = self._embedded_bearer_token
        if server.is_remote and server.endpoint and authorization and embedded_bearer_token:
            entry = mcp_server_entry(self, server, package, "${CLAUDE_PLUGIN_ROOT}")
            entry.setdefault("headers", {})["Authorization"] = f"Bearer {embedded_bearer_token}"
            return entry

        entry = mcp_server_entry(self, server, package, "${CLAUDE_PLUGIN_ROOT}")
        if (
            server.is_remote
            and authorization
            and authorization.source.value == "literal"
            and authorization.value
        ):
            # A literal secret only reaches this target through an imported
            # HTTP header. Codex receives the exact header value, including
            # its scheme, so it has no install-time token prompt.
            entry.setdefault("headers", {})["Authorization"] = authorization.value
            return entry
        if server.is_remote and authorization and authorization.secret:
            # Codex reads this value from the user's environment and constructs
            # the Authorization: Bearer header itself.
            entry.pop("headers", None)
            entry["bearer_token_env_var"] = bearer_token_env_name(server.name)
        return entry

    _embedded_bearer_token: str | None = None

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        self._embedded_bearer_token = package.options_for(self.name).get("_embedded_bearer_token")
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
                    server.name: self._plugin_mcp_entry(package, server)
                    for server in package.mcp_servers
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
        self.stage_portable_payload(package, plugin_dir)
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
        steps = [
            "1. Extract `"
            f"codex-marketplace-{package.metadata.version}.zip` from "
            "`dist/packages/` into a folder.",
            "2. Click Codex's **Settings** gear, then choose **Codex Settings** to open the "
            "Settings UI.",
            "3. Open **Plugins → Add → + Add a marketplace** and select the extracted folder "
            "(it contains `.agents/plugins/marketplace.json`).",
            "4. Adding a marketplace only makes its plugin available; it does not replace an "
            "existing plugin or activate the new one.",
            "5. Install and enable the new plugin with "
            f"`codex plugin add {plugin_name}@{plugin_name}-marketplace` in PowerShell "
            "(or choose **Install** for it in the Plugins list).",
            "6. If an older plugin provides the same MCP server, remove it first with "
            "`codex plugin remove <old-plugin>@<old-marketplace>` so Codex cannot keep using "
            "the old server definition.",
        ]
        for server in package.mcp_servers:
            authorization = server.headers.get("Authorization")
            if (
                server.is_remote
                and authorization
                and authorization.secret
                and authorization.source.value != "literal"
                and not package.options_for(self.name).get("_embedded_bearer_token")
            ):
                env_name = bearer_token_env_name(server.name)
                steps.append(
                    "7. Set the required token once for your Windows user: "
                    f"`[Environment]::SetEnvironmentVariable('{env_name}', "
                    "'<token-without-Bearer>', 'User')`. Close and reopen Codex afterward. "
                    "The token is never stored in the package."
                )
                break
        if package.options_for(self.name).get("_embedded_bearer_token") or any(
            server.is_remote
            and (authorization := server.headers.get("Authorization"))
            and authorization.source.value == "literal"
            and authorization.secret
            for server in package.mcp_servers
        ):
            steps.append(
                "The bearer token is embedded in this Codex package. Treat its ZIP and extracted "
                "folder as secret material and do not share them."
            )
        steps.append(
            "The plugin contains its skills and MCP server configuration; start a new thread "
            "after installation."
        )
        return steps
