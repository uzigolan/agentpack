"""Base class and shared helpers for target adapters.

Adapters must not read the source tree directly beyond the paths carried on
the normalized model, and must never execute anything.
"""

from __future__ import annotations

import zipfile
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

    def install_steps(self, package: AgentPackage) -> list[str]:  # noqa: ARG002
        """Markdown lines telling a user how to install this target's artifacts."""
        return []

    def validate(self, package: AgentPackage) -> Diagnostics:  # noqa: ARG002
        return Diagnostics()

    # -- shared helpers ----------------------------------------------------
    def stage_skill(
        self, skill: Skill, dest: Path, mode: KnowledgeMode = KnowledgeMode.SERVED
    ) -> list[str]:
        """Copy one skill into ``dest``/<skill name>.

        In SERVED mode the ``references/`` corpus is stripped and SKILL.md is
        stamped, so a runtime version check can tell which mode is installed.
        """
        skill_dir = dest / skill.name
        exclude = ("references",) if mode is KnowledgeMode.SERVED else ()
        if skill.source_archive:
            prefix = f"{skill.archive_root.rstrip('/')}/" if skill.archive_root else ""
            written = []
            with zipfile.ZipFile(skill.source_archive) as zf:
                for member in sorted(zf.infolist(), key=lambda item: item.filename):
                    if member.is_dir() or not member.filename.startswith(prefix):
                        continue
                    relative = member.filename.removeprefix(prefix)
                    if not relative or relative == "SKILL.md":
                        continue
                    if mode is KnowledgeMode.SERVED and relative.startswith("references/"):
                        continue
                    target = skill_dir / Path(relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(member))
                    written.append(f"{skill.name}/{relative}")
                skill_text = zf.read(f"{prefix}SKILL.md").decode("utf-8")
            write_text(skill_dir / "SKILL.md", skill_text)
        else:
            written = [
                f"{skill.name}/{p}" for p in copy_tree(skill.source_dir, skill_dir, exclude=exclude)
            ]

        if mode is KnowledgeMode.SERVED:
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
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

    def stage_portable_payload(self, package: AgentPackage, dest: Path) -> list[str]:
        """Copy an imported portable runtime/config payload into an artifact root."""
        if not package.portable_payload:
            return []
        return copy_tree(package.portable_payload.source_dir, dest)

    def package_path(self, package: AgentPackage, value: str, root: str) -> str:
        """Resolve the producer's package-root placeholder for one target."""
        if not package.portable_payload:
            return value
        return value.replace(package.portable_payload.package_root_placeholder, root)

    def user_input_rows(self, package: AgentPackage) -> list[tuple[str, str, EnvVar]]:
        return [
            (server.name, key, var)
            for server in package.mcp_servers
            for key, var in sorted(server.user_inputs().items())
        ]

    def placeholder(self, key: str, var: EnvVar) -> str:
        """Value written when the target cannot prompt the user.

        Never a real secret: generic adapters do not receive stored secrets.
        """
        if var.default and not var.secret:
            return var.default
        if var.value and not var.secret:
            return var.value
        return f"<{key}>"

    def required_values_table(self, package: AgentPackage) -> list[str]:
        inputs = self.user_input_rows(package)
        if not inputs:
            return ["None."]
        return [
            "| Server | Key | Secret | Required | Description |",
            "|---|---|---|---|---|",
            *(
                f"| {srv} | `{key}` | {'yes' if var.secret else 'no'} | "
                f"{'yes' if var.required else 'no'} | {var.description or ''} |"
                for srv, key, var in inputs
            ),
            "",
            "Secrets are never embedded in this package. Supply them during or "
            "after install.",
        ]

    def readme(self, package: AgentPackage) -> str:
        caps = self.capabilities()
        meta = package.metadata
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
            *self.install_steps(package),
            "",
            "## Required values",
            "",
            *self.required_values_table(package),
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
            if v.source.value == "literal" and not v.secret and v.value is not None
        }
