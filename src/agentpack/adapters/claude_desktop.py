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

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

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

BRIDGE_EXECUTABLE = "agentpack-http-bridge-setup.exe"
BRIDGE_SOURCE = Path(__file__).resolve().parents[3] / "bridge"

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


def _windows_bridge() -> Path:
    """Build a source-versioned bridge once and embed it in the MCPB."""
    digest = hashlib.sha256()
    for source in ("main.go", "go.mod", "go.sum"):
        digest.update((BRIDGE_SOURCE / source).read_bytes())
    revision = digest.hexdigest()[:12]
    output = Path(tempfile.gettempdir()) / "agentpack-bridge" / revision / BRIDGE_EXECUTABLE
    if output.is_file():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "go",
                "build",
                "-ldflags",
                f"-X main.bridgeVersion={revision}",
                "-o",
                str(output),
                ".",
            ],
            cwd=BRIDGE_SOURCE,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        message = "HTTP MCPB packaging requires Go to build AgentPack's Windows bridge"
        raise RuntimeError(message) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"could not build AgentPack's Windows bridge: {exc.stderr}") from exc
    return output


def _archive_transport_label(server: MCPServer) -> str:
    """Return a readable, Windows-safe transport label for an MCPB filename."""
    if not server.is_remote:
        return TransportType.STDIO.value

    assert server.endpoint is not None
    hostname = urlsplit(server.endpoint.url).hostname
    if not hostname:
        return server.transport.value
    safe_hostname = "".join(
        char if char.isalnum() or char in ".-" else "-" for char in hostname.lower()
    ).strip(".-")
    return f"{server.transport.value}-{safe_hostname or 'remote'}"


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
                "through AgentPack's bundled Windows HTTP bridge. On first launch it "
                "installs under `%LOCALAPPDATA%\\AgentPack\\bridge`; no Node.js, Python, "
                "or producer checkout is required."
            ),
        )

    def validate(self, package: AgentPackage) -> Diagnostics:
        diags = Diagnostics()
        for server in package.mcp_servers:
            if server.is_remote:
                diags.info(
                    AP2201,
                    f"'{server.name}': bundled with AgentPack's Windows HTTP bridge",
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
            is_bearer_token = key.lower() == "authorization" and var.secret
            entry = {
                "type": var.type,
                "title": var.title or ("Bearer token" if is_bearer_token else key),
                "description": var.description
                or (
                    "Token only; AgentPack adds the `Bearer ` Authorization scheme automatically."
                    if is_bearer_token
                    else f"Value for {key}"
                ),
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
            bridge_args = ["--url", server.endpoint.url]
            for key, var in sorted(server.headers.items()):
                # Claude MCPBs must never carry an imported secret. Treat a
                # stored HTTP credential exactly like a normal Claude prompt.
                prompt_value = var.source.value == "user" or var.secret
                value = declare(key, var) if prompt_value else (var.value or "")
                if key.lower() == "authorization" and prompt_value and var.secret:
                    value = f"Bearer {value}"
                bridge_args += ["--header", f"{key}: {value}"]
            command = f"${{__dirname}}/server/{BRIDGE_EXECUTABLE}"
            args = bridge_args
            entry_point = f"server/{BRIDGE_EXECUTABLE}"
            runtime = "binary"

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
            if server.is_remote:
                bridge = bundle / "server" / BRIDGE_EXECUTABLE
                bridge.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_windows_bridge(), bridge)
            # One .mcpb per server: an MCPB bundle declares exactly one server.
            specs.append(
                ArchiveSpec(
                    root=f"mcpb/{server.name}",
                    label=f"{server.name}-{_archive_transport_label(server)}",
                    suffix=".mcpb",
                )
            )

        if package.skills:
            # Claude Desktop / Cowork imports this ZIP-shaped artifact using
            # the ``.plugin`` extension. It is deliberately separate from
            # the MCPB server bundle so the skills package is portable.
            plugin_dir = output_dir / "cowork-plugin" / meta.name
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
            specs.append(
                ArchiveSpec(
                    root=f"cowork-plugin/{meta.name}", label="cowork-plugin", suffix=".plugin"
                )
            )

        write_text(output_dir / "README.md", self.readme(package))
        return BuildResult(
            target=self.name,
            output_dir=output_dir,
            artifact_type=ArtifactType.BUNDLE,
            archive_specs=specs,
        )

    def install_steps(self, package: AgentPackage) -> list[str]:
        meta = package.metadata
        bundles = [
            f"   - `{self.name}-{s.name}-{_archive_transport_label(s)}-{meta.version}.mcpb`"
            + (
                " (HTTP bridge installs to `%LOCALAPPDATA%\\AgentPack\\bridge`)"
                if s.is_remote
                else ""
            )
            for s in package.mcp_servers
        ]
        steps = [
            "The installable files are in `dist/packages/` "
            "(run `agentpack package` if they are missing).",
            "",
        ]
        if package.skills:
            steps += [
                "1. Install the skills plugin: **Claude Desktop → Settings → Manage plugins → "
                "Add → Upload plugin**. Drag in or select "
                f"`{self.name}-cowork-plugin-{meta.version}.plugin`. It creates "
                f"one plugin with all {len(package.skills)} skill(s).",
            ]
        steps += [
            "2. Install the MCP extension: **Settings → Extensions → Install extension**. "
            "Select each server bundle:",
            *(bundles or ["   - _no MCP servers in this package_"]),
            "3. Fill in any prompted configuration values, then fully quit Claude Desktop "
            "(including the system tray icon) and relaunch.",
        ]
        return steps

