"""Adapter registry.

Built-in adapters are imported lazily so the core never hard-depends on any
single target, and third-party adapters can join via the
``agentpack.targets`` entry-point group.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentpack.adapters.base import TargetAdapter

_BUILTINS: dict[str, tuple[str, str]] = {
    "claude-desktop": ("agentpack.adapters.claude_desktop", "ClaudeDesktopAdapter"),
    "claude-code": ("agentpack.adapters.claude_code", "ClaudeCodeAdapter"),
    "copilot-vscode": ("agentpack.adapters.copilot_vscode", "CopilotVSCodeAdapter"),
    "copilot-intellij": ("agentpack.adapters.copilot_intellij", "CopilotIntelliJAdapter"),
    "codex": ("agentpack.adapters.codex", "CodexAdapter"),
    "universal": ("agentpack.adapters.universal", "UniversalAdapter"),
}


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
        self._load_external()
        return self._instances.get(name)

    def names(self) -> list[str]:
        self._load_external()
        return sorted(set(_BUILTINS) | set(self._instances))

    def all(self) -> list[TargetAdapter]:
        return [a for a in (self.get(n) for n in self.names()) if a is not None]


registry = AdapterRegistry()
