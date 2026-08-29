"""Generate `dist/INSTALL.md`, the single entry point for a built package.

Each target directory already carries its own README. This is the hub a
recipient reads first: what was produced, which file belongs to which client,
and what they must supply.
"""

from __future__ import annotations

from pathlib import Path

from agentpack.adapters.base import TargetAdapter
from agentpack.models.package import AgentPackage, BuildResult

_ANCHORS = str.maketrans({" ": "-", ".": "", "/": "", "(": "", ")": ""})


def _anchor(title: str) -> str:
    return title.lower().translate(_ANCHORS)


def render(
    package: AgentPackage,
    built: list[tuple[TargetAdapter, BuildResult]],
    out_root: Path,
) -> str:
    meta = package.metadata
    targets = [adapter.name for adapter, _ in built]

    lines = [
        f"# Installing {meta.title} {meta.version}",
        "",
        "**Contents:** [What is inside](#what-is-inside) · [Artifacts](#artifacts) · "
        + " · ".join(f"[{name}](#{_anchor(name)})" for name in targets)
        + " · [Required values](#required-values)",
        "",
        meta.description or "",
        "",
        "> Every artifact below is installed as a package through the client's own "
        "import mechanism. Nothing is copied into a client configuration directory "
        "by hand, and skills are never installed one by one.",
        "",
        "## What is inside",
        "",
        f"- {len(package.skills)} skill(s): "
        + (", ".join(s.name for s in package.skills) or "none"),
        f"- {len(package.mcp_servers)} MCP server(s): "
        + (", ".join(f"{s.name} ({s.transport.value})" for s in package.mcp_servers) or "none"),
        f"- knowledge mode: `{package.build.knowledge.value}`",
        "",
        "## Artifacts",
        "",
        "| File | Client | Type |",
        "|---|---|---|",
    ]

    for adapter, result in built:
        caps = adapter.capabilities()
        flag = " (experimental)" if caps.experimental else ""
        if result.archives:
            for path in result.archives:
                rel = path.relative_to(out_root).as_posix()
                lines.append(f"| `{rel}` | {adapter.name}{flag} | {caps.artifact_type.value} |")
        else:
            rel = result.output_dir.relative_to(out_root).as_posix()
            lines.append(f"| `{rel}/` | {adapter.name}{flag} | {caps.artifact_type.value} |")

    lines += [
        "",
        "Install only the ones for the clients you use. Each is self-contained.",
    ]

    for adapter, result in built:
        caps = adapter.capabilities()
        readme = (result.output_dir / "README.md").relative_to(out_root).as_posix()
        lines += [
            "",
            f"## {adapter.name}",
            "",
            *adapter.install_steps(package),
            "",
            f"Details and limitations: [`{readme}`]({readme}).",
        ]
        if caps.notes:
            lines += ["", f"> {caps.notes}"]

    lines += [
        "",
        "## Required values",
        "",
        "These are never embedded in any artifact. Supply them during or after "
        "install, depending on the client.",
        "",
    ]
    reference = built[0][0] if built else None
    lines += reference.required_values_table(package) if reference else ["None."]

    lines += [
        "",
        "## Verify",
        "",
        "1. Fully restart the client (quit it, do not just close the window).",
        "2. Confirm the MCP server is connected in the client's MCP/tools view.",
        "3. Confirm the skills are listed.",
    ]
    return "\n".join(lines)
