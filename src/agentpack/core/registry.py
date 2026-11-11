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
from agentpack.models.package import ArchiveSpec

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
            shell = "bash" if platform == "Linux" else "powershell"
            marketplace_path = '"<absolute path to extracted package folder>"'
            steps = [
                f"Use Claude Code's {platform} command line.",
                "",
                "For a first install, register the extracted folder as a local marketplace:",
                "",
                f"```{shell}",
                f"claude plugin marketplace add {marketplace_path}",
                f"claude plugin install {plugin}@{plugin}-marketplace --scope user",
                "```",
                "",
                "To update, replace the files at that same marketplace path, then run:",
                "",
                f"```{shell}",
                f"claude plugin marketplace update {plugin}-marketplace",
                f"claude plugin update {plugin}@{plugin}-marketplace",
                "claude plugin list",
                "claude mcp list",
                "```",
                "",
                "To test a new build from a different folder without replacing the installed "
                "plugin, start a one-off session with "
                "`claude --plugin-dir \"<path to the extracted plugin folder>\"`. "
                "Start a new session after updating so Claude Code reloads the plugin and "
                "reconnects "
                "to its MCP server.",
            ]
            if self._runtime == "linux-x86_64":
                steps[5:5] = [
                    f"chmod +x <marketplace-directory>/{plugin}/"
                    "runtime/linux-x86_64/rad-mcp-runtime",
                ]
            return steps
        if self._base.name == "copilot-cli":
            platform = (
                "Windows (PowerShell)"
                if self._runtime == "windows-amd64"
                else "Linux (Bash)"
            )
            shell = "powershell" if self._runtime == "windows-amd64" else "bash"
            test_profile = (
                [
                    'Set `$env:COPILOT_HOME = "$HOME\\.copilot-rad-test"` in PowerShell, '
                    "then install from and run Copilot CLI against the test folder in that same "
                    "terminal."
                ]
                if self._runtime == "windows-amd64"
                else [
                    'Run `export COPILOT_HOME="$HOME/.copilot-rad-test"` in Bash, '
                    "then install from and run Copilot CLI against the test folder in that same "
                    "terminal."
                ]
            )
            return [
                f"Use GitHub Copilot CLI from {platform}.",
                "",
                "For a first install:",
                "",
                f"```{shell}",
                "copilot plugin install <absolute path to the extracted folder>",
                "```",
                "",
                "To update, replace all contents of the same source folder with the new package, "
                "then run:",
                "",
                f"```{shell}",
                f"copilot plugin update {package.metadata.name}",
                "copilot plugin list",
                "```",
                "",
                "Exit Copilot CLI completely and run `copilot` again to start a fresh MCP server "
                "process; starting a new chat in the same process may keep the old server running.",
                "",
                "To test a new package from a different folder without changing the default "
                "plugin profile:",
                *test_profile,
                "Install and verify it with `copilot plugin install <absolute path to the test "
                "plugin folder>`, then run `copilot` and `copilot plugin list` in that terminal. "
                "Close that terminal or unset `COPILOT_HOME` to return to the default profile.",
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
        # Windows' own "Extract All" already wraps a zip's contents in a
        # folder named after the archive; adding arc_root too would
        # double-nest it. Linux `unzip` has no such default, so archives
        # built for linux-x86_64 need arc_root to land in one folder instead
        # of spilling loose files into whatever directory it's run from.
        if self._runtime == "windows-amd64" and result.archive_specs:
            result = result.model_copy(
                update={
                    "archive_specs": [
                        spec.model_copy(update={"arc_root": None})
                        for spec in result.archive_specs
                    ]
                }
            )
        elif self._runtime == "linux-x86_64":
            if result.archive_specs and self._base.name in {"copilot", "copilot-cli"}:
                result = result.model_copy(
                    update={
                        "archive_specs": [
                            spec.model_copy(update={"arc_root": package.metadata.name})
                            for spec in result.archive_specs
                        ]
                    }
                )
            elif not result.archive_specs:
                result = result.model_copy(
                    update={
                        "archive_specs": [
                            ArchiveSpec(root=".", label="", arc_root=package.metadata.name)
                        ]
                    }
                )
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
