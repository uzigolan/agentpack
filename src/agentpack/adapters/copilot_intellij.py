"""GitHub Copilot (JetBrains IDEs) adapter — configuration export.

Shares VS Code's JSON dialect (root key ``servers``) but the file lives in the
JetBrains Copilot plugin directory and skills are read from the project root.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.copilot_vscode import CopilotVSCodeAdapter, build_mcp_json
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArtifactType,
    BuildResult,
    Support,
    TargetCapabilities,
)

USER_CONFIG_PATHS = {
    "Windows": "%LOCALAPPDATA%\\github-copilot\\intellij\\mcp.json",
    "macOS": "~/.config/github-copilot/intellij/mcp.json",
    "Linux": "~/.config/github-copilot/intellij/mcp.json",
}


class CopilotIntelliJAdapter(CopilotVSCodeAdapter):
    name = "copilot-intellij"
    adapter_version = 1
    _client = "the JetBrains Copilot plugin"

    def capabilities(self) -> TargetCapabilities:
        caps = super().capabilities()
        return caps.model_copy(
            update={
                "prompts": Support.PARTIAL,
                "agents": Support.NONE,
                "commands": Support.NONE,
                "experimental": True,
                "notes": (
                    "JetBrains Copilot reads MCP servers from its own `mcp.json` and "
                    "does not have VS Code's `.vscode/mcp.json` workspace override. "
                    "Skills are placed in the project root under `.github/skills/`; "
                    "verify against your plugin version before relying on them."
                ),
            }
        )

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        config = build_mcp_json(self, package)
        write_json(output_dir / "mcp.json", config)

        project = output_dir / "project"
        self.stage_skills(package, project / ".github" / "skills")

        write_text(output_dir / "README.md", self.readme(package, self._install_steps()))
        return BuildResult(
            target=self.name, output_dir=output_dir, artifact_type=ArtifactType.CONFIG_EXPORT
        )

    def _install_steps(self) -> list[str]:
        paths = "\n".join(f"   - {os}: `{p}`" for os, p in USER_CONFIG_PATHS.items())
        return [
            "The JetBrains Copilot plugin has no import container, so this package is "
            "delivered as a **project overlay** plus an MCP configuration fragment.",
            "",
            "1. Unzip `project/` over the root of your IDE project (gives you "
            "`.github/skills/`); commit it with the project.",
            "2. Open **Settings → Languages & Frameworks → GitHub Copilot → Model "
            "Context Protocol → Configure** and merge the `servers` and `inputs` keys "
            "from `mcp.json`. The file lives at:",
            "",
            paths,
            "",
            "3. Restart the IDE completely, open Copilot Chat, switch to **Agent** mode "
            "and accept the MCP trust prompt.",
            "4. Verify with `/mcp list` and `/skills list`.",
        ]
