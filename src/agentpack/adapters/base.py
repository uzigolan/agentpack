"""Base class and shared helpers for target adapters.

Adapters must not read the source tree directly beyond the paths carried on
the normalized model, and must never execute anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from agentpack.core.diagnostics import Diagnostics
from agentpack.core.fsutil import copy_tree, write_text
from agentpack.models.package import (
    SERVED_STAMP,
    AgentPackage,
    BuildResult,
    EnvVar,
    KnowledgeMode,
    MCPServer,
    Skill,
    TargetCapabilities,
)


class TargetAdapter(ABC):
    name: str = "unnamed"
    adapter_version: int = 1

    @abstractmethod
    def capabilities(self) -> TargetCapabilities: ...

    @abstractmethod
    def build(self, package: AgentPackage, output_dir: Path) -> BuildResult: ...

    def validate(self, package: AgentPackage) -> Diagnostics:  # noqa: ARG002
        return Diagnostics()

    # -- shared helpers ----------------------------------------------------
    def stage_skill(
        self, skill: Skill, dest: Path, mode: KnowledgeMode = KnowledgeMode.BUNDLED
    ) -> list[str]:
        """Copy one skill into ``dest``/<skill name>.

        In SERVED mode the ``references/`` corpus is stripped and SKILL.md is
        stamped, so a runtime version check can tell which mode is installed.
        """
        skill_dir = dest / skill.name
        exclude = ("references",) if mode is KnowledgeMode.SERVED else ()
        written = [
            f"{skill.name}/{p}" for p in copy_tree(skill.source_dir, skill_dir, exclude=exclude)
        ]

        if mode is KnowledgeMode.SERVED:
            text = skill.skill_md.read_text(encoding="utf-8")
            if SERVED_STAMP not in text:
                write_text(skill_dir / "SKILL.md", f"{text.rstrip()}\n\n{SERVED_STAMP}")
        return sorted(written)

    def stage_skills(
        self, package: AgentPackage, dest: Path, mode: KnowledgeMode | None = None
    ) -> list[str]:
        mode = mode or package.build.knowledge
        out: list[str] = []
        for skill in package.skills:
            out.extend(self.stage_skill(skill, dest, mode))
        return out

    def user_input_rows(self, package: AgentPackage) -> list[tuple[str, str, EnvVar]]:
        return [
            (server.name, key, var)
            for server in package.mcp_servers
            for key, var in sorted(server.user_inputs().items())
        ]

    def placeholder(self, key: str, var: EnvVar) -> str:
        """Value written when the target cannot prompt the user.

        Never a real secret: AgentPack does not read the local environment.
        """
        if var.default and not var.secret:
            return var.default
        if var.value and not var.secret:
            return var.value
        return f"<{key}>"

    def readme(self, package: AgentPackage, sections: list[str]) -> str:
        caps = self.capabilities()
        meta = package.metadata
        inputs = self.user_input_rows(package)
        lines = [
            f"# {meta.title} — {self.name} package",
            "",
            f"Version **{meta.version}** · artifact type **{caps.artifact_type.value}**"
            + (" · **experimental**" if caps.experimental else ""),
            "",
            "**Contents:** [What is inside](#what-is-inside) · [Install](#install) · "
            "[Required values](#required-values) · [Verify](#verify) · "
            "[Limitations](#limitations)",
            "",
            meta.description or "",
            "",
            "## What is inside",
            "",
            f"- {len(package.skills)} skill(s): "
            + (", ".join(s.name for s in package.skills) or "none"),
            f"- {len(package.mcp_servers)} MCP server(s): "
            + (", ".join(s.name for s in package.mcp_servers) or "none"),
            f"- knowledge mode: `{package.build.knowledge.value}`",
            "",
            "## Install",
            "",
            "> Everything here is installed as a package through the client's own "
            "import mechanism. Nothing is copied into the client's configuration "
            "directories by hand, and skills are never installed one by one.",
            "",
            *sections,
            "",
            "## Required values",
            "",
        ]
        if inputs:
            lines += ["| Server | Key | Secret | Required | Description |", "|---|---|---|---|---|"]
            lines += [
                f"| {srv} | `{key}` | {'yes' if var.secret else 'no'} | "
                f"{'yes' if var.required else 'no'} | {var.description or ''} |"
                for srv, key, var in inputs
            ]
            lines += [
                "",
                "Secrets are never embedded in this package. Supply them during or "
                "after install.",
            ]
        else:
            lines.append("None.")

        lines += [
            "",
            "## Verify",
            "",
            "1. Fully restart the client (quit it, do not just close the window).",
            "2. Confirm the MCP server is connected in the client's MCP/tools view.",
            "3. Confirm the skills are listed.",
            "",
            "## Limitations",
            "",
            caps.notes or "None recorded.",
        ]
        return "\n".join(lines)

    def mcp_env_literals(self, server: MCPServer) -> dict[str, str]:
        return {
            k: v.value or ""
            for k, v in server.environment.items()
            if v.source.value == "literal" and v.value is not None
        }
