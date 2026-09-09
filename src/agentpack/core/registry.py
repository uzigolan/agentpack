"""Adapter registry.

Built-in adapters are imported lazily so the core never hard-depends on any
single target, and third-party adapters can join via the
``agentpack.targets`` entry-point group.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from agentpack.adapters.base import TargetAdapter
from agentpack.core.fsutil import write_text

if TYPE_CHECKING:
    from agentpack.models.package import AgentPackage

_BUILTINS: dict[str, tuple[str, str]] = {
    "claude-desktop": ("agentpack.adapters.claude_desktop", "ClaudeDesktopAdapter"),
    "claude-code": ("agentpack.adapters.claude_code", "ClaudeCodeAdapter"),
    "copilot": ("agentpack.adapters.copilot_vscode", "CopilotPluginAdapter"),
    "copilot-cli": ("agentpack.adapters.copilot_vscode", "CopilotCLIAdapter"),
    "codex": ("agentpack.adapters.codex", "CodexAdapter"),
    "universal": ("agentpack.adapters.universal", "UniversalAdapter"),
}

_PLATFORM_TARGETS: dict[str, tuple[str, str]] = {
    "universal-win": ("universal", "windows-amd64"),
    "universal-linux": ("universal", "linux-x86_64"),
    "claude-desktop-win": ("claude-desktop", "windows-amd64"),
    "claude-code-win": ("claude-code", "windows-amd64"),
    "claude-code-cli-linux": ("claude-code", "linux-x86_64"),
    "copilot-win": ("copilot", "windows-amd64"),
    "copilot-cli-win": ("copilot-cli", "windows-amd64"),
    "copilot-cli-linux": ("copilot-cli", "linux-x86_64"),
    "codex-win": ("codex", "windows-amd64"),
    "codex-cli-linux": ("codex", "linux-x86_64"),
}


class _PlatformAdapter(TargetAdapter):
    def __init__(self, name: str, base: TargetAdapter, runtime: str) -> None:
        self.name = name
        self._base = base
        self._runtime = runtime
        self.adapter_version = base.adapter_version

    def capabilities(self):
        return self._base.capabilities()

    def validate(self, package: AgentPackage):
        return self._base.validate(package)

    def install_steps(self, package: AgentPackage):
        if self._base.name == "claude-code":
            plugin = package.metadata.name
            platform = "Linux" if self._runtime == "linux-x86_64" else "Windows"
            steps = [
                f"Use Claude Code's {platform} command line to replace an older plugin, then install and verify this one:",
                "",
                "```bash",
                "claude plugin list",
                "claude plugin uninstall <old-plugin>@<old-marketplace>",
                "claude plugin marketplace remove <old-marketplace>",
                "claude plugin marketplace add <absolute path to marketplace-directory>",
                f"claude plugin install {plugin}@{plugin}-marketplace",
                "claude plugin list",
                "claude mcp list",
                "claude",
                "```",
                "",
                "Run the uninstall and marketplace removal commands only when replacing an older plugin. "
                "Start a new Claude Code session after installation so it loads the plugin and reconnects to its MCP server.",
            ]
            if self._runtime == "linux-x86_64":
                steps[3:3] = [
                    f"chmod +x <marketplace-directory>/{plugin}/runtime/linux-x86_64/rad-mcp-runtime",
                ]
            return steps
        if self._base.name == "copilot-cli":
            return [
                "Use the GitHub Copilot CLI to replace an older plugin, then install and verify this one:",
                "",
                "```bash",
                "copilot plugin list",
                "copilot plugin uninstall <old-plugin>",
                "copilot plugin install <absolute path to the extracted folder>",
                "copilot plugin list",
                "```",
                "",
                "Run the uninstall command only when replacing an older plugin, then start a new Copilot CLI session.",
            ]
        if self._base.name == "codex":
            plugin = package.metadata.name.lower().replace("_", "-").replace(".", "-")
            return [
                "Use the Codex command line to replace an older plugin, then install and verify this one:",
                "",
                "```bash",
                "codex plugin list",
                "codex plugin remove <old-plugin>@<old-marketplace>",
                f"codex plugin add {plugin}@{plugin}-marketplace",
                "codex plugin list",
                "```",
                "",
                "Run the removal command only when replacing an older plugin, then start a new Codex session.",
            ]
        return self._base.install_steps(package)

    def build(self, package: AgentPackage, output_dir):
        package = package.model_copy(deep=True)
        for server in package.mcp_servers:
            if not server.command:
                continue
            executable = server.command.executable.replace(
                "/runtime/windows-amd64/", f"/runtime/{self._runtime}/"
            )
            executable = executable.replace(
                "\\runtime\\windows-amd64\\", f"\\runtime\\{self._runtime}\\"
            )
            if self._runtime == "linux-x86_64" and executable.endswith(".exe"):
                executable = executable[:-4]
            server.command = server.command.model_copy(update={"executable": executable})
        result = self._base.build(package, output_dir)
        if self._base.name in {"claude-code", "copilot-cli", "codex"}:
            write_text(output_dir / "README.md", self.readme(package))
        if self._base.name == "codex":
            plugin = package.metadata.name.lower().replace("_", "-").replace(".", "-")
            write_text(output_dir / "plugins" / plugin / "README.md", self.readme(package))
        return result


class AdapterRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, TargetAdapter] = {}
        self._external_loaded = False

    def register(self, name: str, adapter: TargetAdapter) -> None:
        self._instances[name] = adapter

    def _load_external(self) -> None:
        if self._external_loaded:
            return
        self._external_loaded = True
        for ep in entry_points(group="agentpack.targets"):
            try:
                self._instances.setdefault(ep.name, ep.load()())
            except Exception:  # noqa: BLE001 - a broken plugin must not kill the CLI
                continue

    def get(self, name: str) -> TargetAdapter | None:
        if name in self._instances:
            return self._instances[name]
        if name in _BUILTINS:
            module, cls = _BUILTINS[name]
            adapter = getattr(import_module(module), cls)()
            self._instances[name] = adapter
            return adapter
        if name in _PLATFORM_TARGETS:
            base_name, runtime = _PLATFORM_TARGETS[name]
            base = self.get(base_name)
            if base is None:
                return None
            adapter = _PlatformAdapter(name, base, runtime)
            self._instances[name] = adapter
            return adapter
        self._load_external()
        return self._instances.get(name)

    def names(self) -> list[str]:
        self._load_external()
        return sorted(set(_BUILTINS) | set(_PLATFORM_TARGETS) | set(self._instances))

    def all(self) -> list[TargetAdapter]:
        return [a for a in (self.get(n) for n in self.names()) if a is not None]


registry = AdapterRegistry()
