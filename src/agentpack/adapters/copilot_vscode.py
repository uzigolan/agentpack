"""GitHub Copilot (VS Code) adapter — configuration export.

Encoded facts:
- The MCP config root key is ``servers`` (a very common copy/paste error is to
  use Claude's ``mcpServers`` here; it silently does nothing).
- User-level config: ``%APPDATA%\\Code\\User\\mcp.json`` on Windows,
  ``~/Library/Application Support/Code/User/mcp.json`` on macOS,
  ``~/.config/Code/User/mcp.json`` on Linux. Workspace-level: ``.vscode/mcp.json``.
- Secrets use the ``inputs`` array plus ``${input:<id>}`` references, so nothing
  sensitive is written into the file itself.
- Skills are directories under ``.github/skills/<name>/SKILL.md`` in a workspace.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArtifactType,
    BuildResult,
    EnvVar,
    MCPServer,
    Support,
    TargetCapabilities,
)

USER_CONFIG_PATHS = {
    "Windows": "%APPDATA%\\Code\\User\\mcp.json",
    "macOS": "~/Library/Application Support/Code/User/mcp.json",
    "Linux": "~/.config/Code/User/mcp.json",
}


def input_id(server: str, key: str) -> str:
    return f"{server}-{key.lower().replace('_', '-')}"


def build_mcp_json(adapter: TargetAdapter, package: AgentPackage) -> dict:
    """Shared by the VS Code and IntelliJ Copilot adapters."""
    inputs: list[dict] = []
    servers: dict[str, dict] = {}

    for server in package.mcp_servers:
        entry: dict
        if server.is_remote and server.endpoint:
            entry = {"type": "http", "url": server.endpoint.url}
            headers = {}
            for key, var in sorted(server.headers.items()):
                headers[key] = _value_ref(server, key, var, inputs)
            if headers:
                entry["headers"] = headers
        else:
            assert server.command is not None
            entry = {
                "type": "stdio",
                "command": server.command.executable,
                "args": list(server.command.args),
            }
            if server.command.cwd:
                entry["cwd"] = server.command.cwd

        env = adapter.mcp_env_literals(server)
        for key, var in sorted(server.environment.items()):
            if var.source.value == "user":
                env[key] = _value_ref(server, key, var, inputs)
        if env:
            entry["env"] = env
        servers[server.name] = entry

    config: dict = {}
    if inputs:
        config["inputs"] = inputs
    config["servers"] = servers
    return config


def _value_ref(server: MCPServer, key: str, var: EnvVar, inputs: list[dict]) -> str:
    ident = input_id(server.name, key)
    if not any(i["id"] == ident for i in inputs):
        entry = {
            "type": "promptString",
            "id": ident,
            "description": var.description or f"{server.name}: {key}",
            "password": var.secret,
        }
        if var.default and not var.secret:
            entry["default"] = var.default
        inputs.append(entry)
    return f"${{input:{ident}}}"


class CopilotVSCodeAdapter(TargetAdapter):
    name = "copilot-vscode"
    adapter_version = 1
    _client = "VS Code"

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            skills=Support.FULL,
            mcp_stdio=Support.FULL,
            mcp_http=Support.FULL,
            user_config=Support.FULL,
            prompts=Support.FULL,
            agents=Support.PARTIAL,
            commands=Support.PARTIAL,
            hooks=Support.NONE,
            artifact_type=ArtifactType.CONFIG_EXPORT,
            notes=(
                "There is no importable plugin container for Copilot in VS Code, so "
                "AgentPack emits a drop-in workspace tree plus an `mcp.json` fragment "
                "to merge into your user config. Secrets are collected by VS Code via "
                "`inputs`/`${input:...}` and are never written to disk by AgentPack."
            ),
        )

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        workspace = output_dir / "workspace"
        config = build_mcp_json(self, package)

        write_json(workspace / ".vscode" / "mcp.json", config)
        write_json(output_dir / "mcp.json", config)

        self.stage_skills(package, workspace / ".github" / "skills")
        for prompt in package.prompts:
            dest = workspace / ".github" / "prompts" / prompt.relative_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(prompt.source.read_bytes())
        for agent in package.agents:
            dest = workspace / ".github" / "agents" / agent.relative_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(agent.source.read_bytes())

        write_text(output_dir / "README.md", self.readme(package, self._install_steps()))
        return BuildResult(
            target=self.name, output_dir=output_dir, artifact_type=ArtifactType.CONFIG_EXPORT
        )

    def _install_steps(self) -> list[str]:
        paths = "\n".join(f"   - {os}: `{p}`" for os, p in USER_CONFIG_PATHS.items())
        return [
            "VS Code has no plugin container for Copilot capabilities, so this package "
            "is delivered as a **workspace overlay** — it lands in your own repository, "
            "not in a VS Code or Copilot configuration directory.",
            "",
            "1. Unzip `workspace/` over the root of the repository you want these "
            "capabilities in. That gives you `.vscode/mcp.json` and "
            "`.github/skills/` in one step; commit them with the repo.",
            "2. Reload the window, open Copilot Chat, switch to **Agent** mode and start "
            "the server from the MCP view. You will be prompted for any `${input:...}` "
            "values on first use.",
            "",
            "If you want the servers available in every workspace instead, merge the "
            "`servers` and `inputs` keys from `mcp.json` into your user file:",
            "",
            paths,
            "",
            "> The root key is `servers`. Do **not** rename it to `mcpServers` — "
            f"{self._client} ignores that spelling.",
        ]
