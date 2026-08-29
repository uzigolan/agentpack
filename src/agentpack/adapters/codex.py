"""OpenAI Codex adapter — TOML configuration export.

Encoded facts:
- Config file is ``~/.codex/config.toml`` (``%USERPROFILE%\\.codex\\config.toml``).
  It is **TOML**, not JSON — the single biggest difference from every other
  target here.
- Servers are declared as ``[mcp_servers.<name>]`` with ``command``/``args``/``env``.
- Environment values are a nested ``[mcp_servers.<name>.env]`` table.
- Skills are directories under ``~/.agents/skills/<name>/SKILL.md``.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.core.diagnostics import AP2201, Diagnostics
from agentpack.core.fsutil import write_text
from agentpack.models.package import (
    AgentPackage,
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
            user_config=Support.NONE,
            prompts=Support.PARTIAL,
            agents=Support.NONE,
            commands=Support.NONE,
            hooks=Support.NONE,
            artifact_type=ArtifactType.CONFIG_EXPORT,
            notes=(
                "Codex configuration is TOML. Remote MCP servers are only reachable "
                "through the experimental streamable-HTTP client, and bearer tokens must "
                "come from an environment variable rather than the config file, so "
                "AgentPack emits `bearer_token_env_var` instead of the token itself."
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
        write_text(output_dir / "config.toml", self._config_toml(package))
        self.stage_skills(package, output_dir / "skills")
        write_text(output_dir / "README.md", self.readme(package, self._install_steps()))
        return BuildResult(
            target=self.name, output_dir=output_dir, artifact_type=ArtifactType.CONFIG_EXPORT
        )

    def _install_steps(self) -> list[str]:
        return [
            "Codex has no plugin or extension container, so this target is a "
            "configuration export: one archive, applied once.",
            "",
            "1. Append the tables from `config.toml` to your Codex config:",
            "   - Windows: `%USERPROFILE%\\.codex\\config.toml`",
            "   - macOS/Linux: `~/.codex/config.toml`",
            "2. Replace every `<KEY>` placeholder, and export any token referenced by "
            "`bearer_token_env_var` in your shell.",
            "3. Extract the whole `skills/` directory from this archive into your agent "
            "skills directory in one step — do not pick skills individually:",
            "   - Windows: `%USERPROFILE%\\.agents\\skills\\`",
            "   - macOS/Linux: `~/.agents/skills/`",
            "4. Restart Codex (CLI session or IDE extension).",
        ]
