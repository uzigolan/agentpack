"""Universal adapter — client-neutral, loss-free package.

This is the archival format: it keeps every capability verbatim plus a
machine-readable ``plugin.json`` index, so a package can be re-imported by
``agentpack`` itself or consumed by a client AgentPack does not know about.
"""

from __future__ import annotations

from pathlib import Path

from agentpack import API_VERSION, __version__
from agentpack.adapters.base import TargetAdapter
from agentpack.core.fsutil import write_json, write_text
from agentpack.models.package import (
    AgentPackage,
    ArtifactType,
    BuildResult,
    Support,
    TargetCapabilities,
)


class UniversalAdapter(TargetAdapter):
    name = "universal"
    adapter_version = 1

    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            skills=Support.FULL,
            mcp_stdio=Support.FULL,
            mcp_http=Support.FULL,
            user_config=Support.FULL,
            prompts=Support.FULL,
            agents=Support.FULL,
            commands=Support.FULL,
            hooks=Support.FULL,
            artifact_type=ArtifactType.ARCHIVE,
            spec_version=API_VERSION,
            notes=(
                "No client consumes this format directly. It is the loss-free "
                "interchange artifact: keep it for archival, re-packaging and diffing."
            ),
        )

    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult:
        meta = package.metadata
        index = {
            "apiVersion": API_VERSION,
            "kind": "AgentPackage",
            "agentpackVersion": __version__,
            "metadata": meta.model_dump(by_alias=True, exclude_none=True),
            "knowledgeMode": package.build.knowledge.value,
            "skills": [
                {
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "path": f"skills/{s.name}",
                    "hasReferences": s.has_references,
                }
                for s in package.skills
            ],
            "mcpServers": [
                {
                    "name": s.name,
                    "transport": s.transport.value,
                    "path": f"mcp/{s.name}.yaml",
                    "userInputs": sorted(s.user_inputs()),
                    "capabilities": s.capabilities.model_dump(),
                }
                for s in package.mcp_servers
            ],
            "prompts": [p.relative_path for p in package.prompts],
            "agents": [a.relative_path for a in package.agents],
            "commands": [c.relative_path for c in package.commands],
            "hooks": [h.relative_path for h in package.hooks],
        }
        write_json(output_dir / "plugin.json", index)

        self.stage_skills(package, output_dir / "skills")

        for server in package.mcp_servers:
            if server.source_file and server.source_file.is_file():
                dest = output_dir / "mcp" / f"{server.name}.yaml"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(server.source_file.read_bytes())

        for assets, folder in (
            (package.prompts, "prompts"),
            (package.agents, "agents"),
            (package.commands, "commands"),
            (package.hooks, "hooks"),
            (package.assets, "assets"),
        ):
            for asset in assets:
                dest = output_dir / folder / asset.relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(asset.source.read_bytes())

        write_text(output_dir / "README.md", self.readme(package))
        return BuildResult(
            target=self.name, output_dir=output_dir, artifact_type=ArtifactType.ARCHIVE
        )

    def install_steps(self, package: AgentPackage) -> list[str]:  # noqa: ARG002
        return [
            "This artifact is not installed directly. Use it to re-build a "
            "client package:",
            "",
            "```bash",
            "agentpack build --target claude-desktop --target copilot-vscode",
            "```",
            "",
            "`plugin.json` indexes every capability in this directory.",
        ]
