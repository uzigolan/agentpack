"""Claude Desktop adapter — MCPB bundle + skills.

Verified facts encoded here (from a production toolkit that ships this format):
- ``manifest.json`` with ``manifest_version`` "0.3", ``server.type`` one of
  node/python/binary, and ``server.mcp_config``.
- ``user_config`` entries are prompted at import time; this is how secrets stay
  out of the artifact. ``${user_config.<key>}`` and ``${__dirname}`` interpolate.
- A ``.mcpb`` file is a plain ZIP of the bundle directory.
- Absolute paths baked into ``user_config.default`` are machine-specific; the
  README therefore tells the user to re-point them rather than assuming they
  travel.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.core.diagnostics import AP2201, AP2401, Diagnostics
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArchiveSpec,
    ArtifactType,
    BuildResult,
    MCPServer,
    Support,
    TargetCapabilities,
    TransportType,
)

MANIFEST_VERSION = "0.3"

# Claude Desktop only launches local processes, so a remote server is reached by
# bundling a stdio<->HTTP proxy. `mcp-remote` is the de-facto one and needs no
# code from us, which keeps the "never ship a runtime" rule intact.
REMOTE_BRIDGE_PACKAGE = "mcp-remote"

_RUNTIME_BY_EXECUTABLE = {
    "node": "node",
    "npx": "node",
    "bun": "node",
    "python": "python",
    "python3": "python",
    "py": "python",
    "uv": "python",
    "uvx": "python",
}


def _runtime(executable: str) -> str:
    stem = Path(executable).stem.lower()
    return _RUNTIME_BY_EXECUTABLE.get(stem, "binary")


def _entry_point(executable: str, args: list[str]) -> str:
    """First non-flag argument (the module/package actually launched)."""
    for index, arg in enumerate(args):
        if arg.startswith("-"):
            continue
        if index and args[index - 1] in ("-m", "--module"):
            return arg
        return arg
    return executable


class ClaudeDesktopAdapter(TargetAdapter):
    name = "claude-desktop"
    adapter_version = 1

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            skills=Support.FULL,
            mcp_stdio=Support.FULL,
            mcp_http=Support.PARTIAL,
            user_config=Support.FULL,
            prompts=Support.PARTIAL,
            agents=Support.NONE,
            commands=Support.NONE,
            hooks=Support.NONE,
            artifact_type=ArtifactType.BUNDLE,
            spec_version=f"mcpb manifest {MANIFEST_VERSION}",
            notes=(
                "One MCPB bundle declares one MCP server, so a package with several "
                "servers produces several bundles. Skills ship as a single plugin "
                "package installed through the same Install-from-file dialog — never as "
                "loose folders copied into a Claude directory. Claude Desktop only "
                "launches local processes, so remote (http/sse) servers are wired "
                "through `npx -y mcp-remote <url>`, which requires Node.js on the "
                "installing machine. Paths in `user_config.default` are absolute and "
                "must be re-pointed on another machine."
            ),
        )

    def validate(self, package: AgentPackage) -> Diagnostics:
        diags = Diagnostics()
        for server in package.mcp_servers:
            if server.is_remote:
                diags.info(
                    AP2201,
                    f"'{server.name}': bridged with `npx -y {REMOTE_BRIDGE_PACKAGE}`; "
                    "the installing machine needs Node.js",
                    target=self.name,
                )
        if package.commands or package.hooks:
            diags.warning(
                AP2401,
                "commands and hooks are not represented in an MCPB bundle",
                target=self.name,
            )
        return diags

    def _manifest(self, package: AgentPackage, server: MCPServer) -> dict:
        meta = package.metadata
        user_config: dict[str, dict] = {}
        env: dict[str, str] = self.mcp_env_literals(server)

        def declare(key: str, var) -> str:  # noqa: ANN001 - EnvVar
            cfg_key = key.lower().replace("-", "_")
            entry = {
                "type": var.type,
                "title": var.title or key,
                "description": var.description or f"Value for {key}",
                "required": var.required,
                "sensitive": var.secret,
            }
            if var.default and not var.secret:
                entry["default"] = var.default
            user_config[cfg_key] = entry
            return f"${{user_config.{cfg_key}}}"

        for key, var in sorted(server.environment.items()):
            if var.source.value == "user":
                env[key] = declare(key, var)

        if server.transport is TransportType.STDIO and server.command:
            command = server.command.executable
            args = list(server.command.args)
            entry_point = _entry_point(command, args)
            runtime = _runtime(command)
        else:
            assert server.endpoint is not None
            command = "npx"
            args = ["-y", REMOTE_BRIDGE_PACKAGE, server.endpoint.url]
            for key, var in sorted(server.headers.items()):
                value = declare(key, var) if var.source.value == "user" else (var.value or "")
                args += ["--header", f"{key}: {value}"]
            entry_point = REMOTE_BRIDGE_PACKAGE
            runtime = "node"

        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "name": f"{meta.name}-{server.name}",
            "display_name": server.display_name or f"{meta.title} — {server.name}",
            "version": meta.version,
            "description": server.description or meta.description,
            "author": {"name": meta.author_name},
            "server": {
                "type": runtime,
                "entry_point": entry_point,
                "mcp_config": {
                    "command": command,
                    "args": args,
                    **({"env": env} if env else {}),
                },
            },
        }
        if meta.homepage:
            manifest["homepage"] = meta.homepage
        if meta.repository:
            manifest["repository"] = {"type": "git", "url": meta.repository}
        if meta.license:
            manifest["license"] = meta.license
        if meta.keywords:
            manifest["keywords"] = meta.keywords
        if user_config:
            manifest["user_config"] = user_config
        return manifest

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        meta = package.metadata
        specs: list[ArchiveSpec] = []

        for server in package.mcp_servers:
            bundle = output_dir / "mcpb" / server.name
            write_json(bundle / "manifest.json", self._manifest(package, server))
            # One .mcpb per server: an MCPB bundle declares exactly one server.
            specs.append(
                ArchiveSpec(root=f"mcpb/{server.name}", label=server.name, suffix=".mcpb")
            )

        if package.skills:
            plugin_dir = output_dir / "plugin" / meta.name
            write_json(
                plugin_dir / ".claude-plugin" / "plugin.json",
                {
                    "name": meta.name,
                    "description": meta.description,
                    "version": meta.version,
                    "author": {"name": meta.author_name},
                },
            )
            self.stage_skills(package, plugin_dir / "skills")
            specs.append(ArchiveSpec(root=f"plugin/{meta.name}", label="skills"))

        write_text(output_dir / "README.md", self.readme(package, self._install_steps(package)))
        return BuildResult(
            target=self.name,
            output_dir=output_dir,
            artifact_type=ArtifactType.BUNDLE,
            archive_specs=specs,
        )

    def _install_steps(self, package: AgentPackage) -> list[str]:
        meta = package.metadata
        bundles = [
            f"   - `{meta.name}-{self.name}-{s.name}-{meta.version}.mcpb`"
            + (" (remote, needs Node.js)" if s.is_remote else "")
            for s in package.mcp_servers
        ]
        steps = [
            "Run `agentpack package --target claude-desktop` to produce the installable "
            "files in `dist/packages/`.",
            "",
            "1. Claude Desktop → **Settings → Extensions → Install from file** → select "
            "each MCP bundle:",
            *(bundles or ["   - _no MCP servers in this package_"]),
            "2. Fill in the prompted configuration values (see below).",
        ]
        if package.skills:
            steps += [
                f"3. Install the skills package the same way: "
                f"`{meta.name}-{self.name}-skills-{meta.version}.zip`. "
                f"It carries all {len(package.skills)} skill(s) as one plugin — there is "
                "nothing to copy by hand.",
                "4. Fully quit Claude Desktop (including the system tray icon) and relaunch.",
            ]
        else:
            steps.append(
                "3. Fully quit Claude Desktop (including the system tray icon) and relaunch."
            )
        return steps

