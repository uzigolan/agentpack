"""Standalone install guides generated only from distributable package files."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import Path

from agentpack.core.diagnostics import AP1003, AgentPackError
from agentpack.core.fsutil import write_text


@dataclass(frozen=True)
class PackageArtifact:
    path: Path
    target: str
    kind: str
    plugin_name: str | None = None
    marketplace_name: str | None = None
    transport: str | None = None


def _zip_json(path: Path, member: str) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read(member).decode("utf-8"))
    except (KeyError, OSError, json.JSONDecodeError, zipfile.BadZipFile):
        return {}


def _plugin_identity(path: Path, member: str) -> tuple[str | None, str | None]:
    data = _zip_json(path, member)
    plugins = data.get("plugins") or []
    if not plugins:
        return None, None
    plugin = plugins[0]
    return plugin.get("name"), data.get("name")


def scan(packages_dir: Path) -> list[PackageArtifact]:
    """Identify supported target artifacts without reading a project manifest."""
    packages_dir = packages_dir.resolve()
    if not packages_dir.is_dir():
        raise AgentPackError(AP1003, f"packages directory not found: {packages_dir}")

    artifacts: list[PackageArtifact] = []
    for path in sorted(packages_dir.iterdir(), key=lambda item: item.name.lower()):
        name = path.name.lower()
        if path.is_file() and name.startswith("claude-desktop-") and name.endswith(".mcpb"):
            manifest = _zip_json(path, "manifest.json")
            command = ((manifest.get("server") or {}).get("mcp_config") or {}).get("command", "")
            transport = "http" if "bridge" in command or "-http-" in name else "stdio"
            artifacts.append(
                PackageArtifact(path, "Claude Desktop", "MCP extension", transport=transport)
            )
        elif path.is_file() and name.startswith("claude-desktop-") and name.endswith(".plugin"):
            artifacts.append(PackageArtifact(path, "Claude Desktop", "skills plugin"))
        elif path.is_file() and name.startswith("claude-code-") and name.endswith(".zip"):
            plugin, marketplace = _plugin_identity(path, ".claude-plugin/marketplace.json")
            artifacts.append(
                PackageArtifact(path, "Claude Code", "plugin marketplace", plugin, marketplace)
            )
        elif path.is_file() and name.startswith("copilot-") and name.endswith(".zip"):
            manifest = _zip_json(path, "plugin.json")
            artifacts.append(
                PackageArtifact(path, "GitHub Copilot", "plugin", manifest.get("name"))
            )
        elif path.is_file() and name.startswith("codex-marketplace-") and name.endswith(".zip"):
            plugin, marketplace = _plugin_identity(path, ".agents/plugins/marketplace.json")
            artifacts.append(
                PackageArtifact(path, "Codex", "plugin marketplace", plugin, marketplace)
            )
        elif path.is_file() and name.startswith("universal-") and name.endswith(".zip"):
            artifacts.append(PackageArtifact(path, "Universal", "archive"))
    return artifacts


def _names(artifacts: list[PackageArtifact], target: str) -> list[str]:
    return [artifact.path.name for artifact in artifacts if artifact.target == target]


def render_markdown(artifacts: list[PackageArtifact]) -> str:
    lines = [
        "# Package installation guide",
        "",
        "This guide is based only on the files in this folder. Install only the package "
        "for the client you use.",
        "",
        "## Available packages",
        "",
        "| File | Target | Type |",
        "|---|---|---|",
    ]
    for artifact in artifacts:
        detail = f" ({artifact.transport.upper()})" if artifact.transport else ""
        lines.append(f"| `{artifact.path.name}` | {artifact.target} | {artifact.kind}{detail} |")

    desktop = [item for item in artifacts if item.target == "Claude Desktop"]
    if desktop:
        lines += ["", "## Claude Desktop", ""]
        plugins = [item.path.name for item in desktop if item.kind == "skills plugin"]
        extensions = [item for item in desktop if item.kind == "MCP extension"]
        if plugins:
            lines += [
                "1. Open **Settings → Manage plugins → Add → Upload plugin**.",
                f"2. Select `{plugins[0]}` to install the skills.",
            ]
        if extensions:
            lines += ["3. Open **Settings → Extensions → Install extension**."]
            lines += [
                f"4. Select `{item.path.name}` ({item.transport.upper()})."
                for item in extensions
            ]
        lines.append(
            "5. Fully quit Claude Desktop, including its system-tray icon, then reopen it."
        )

    claude_code = [item for item in artifacts if item.target == "Claude Code"]
    if claude_code:
        item = claude_code[0]
        lines += ["", "## Claude Code", "", f"1. Extract `{item.path.name}` to a folder."]
        if item.plugin_name and item.marketplace_name:
            lines += [
                "2. In Claude Code, run:",
                "",
                "```text",
                "/plugin marketplace add <absolute path to extracted folder>",
                f"/plugin install {item.plugin_name}@{item.marketplace_name}",
                "```",
            ]
        else:
            lines.append("2. Add the extracted folder through Claude Code’s Plugins screen.")

    copilot = [item for item in artifacts if item.target == "GitHub Copilot"]
    if copilot:
        lines += [
            "",
            "## GitHub Copilot",
            "",
            f"1. Extract `{copilot[0].path.name}` to a folder.",
            "2. Open Copilot **Settings → Plugins → Install Plugin from Source**.",
            "3. Select the extracted folder, install the plugin, then reload the client.",
        ]

    codex = [item for item in artifacts if item.target == "Codex"]
    if codex:
        item = codex[0]
        lines += ["", "## Codex", "", f"1. Extract `{item.path.name}` to a folder."]
        if item.plugin_name and item.marketplace_name:
            lines += [
                "2. In **Codex Settings → Plugins**, add the extracted folder as a marketplace.",
                f"3. Install `{item.plugin_name}@{item.marketplace_name}` from that marketplace.",
            ]
        else:
            lines.append(
                "2. In **Codex Settings → Plugins**, add the extracted folder as a marketplace."
            )

    universal = _names(artifacts, "Universal")
    if universal:
        lines += [
            "",
            "## Universal archive",
            "",
            f"`{universal[0]}` is an archive for storage or redistribution; it is not "
            "installed directly.",
        ]

    lines += [
        "",
        "## Verify",
        "",
        "1. Restart the client completely.",
        "2. Confirm the package’s MCP tools and skills are visible.",
    ]
    return "\n".join(lines)


def render_html(artifacts: list[PackageArtifact]) -> str:
    rows = "\n".join(
        "<tr><td><code>{}</code></td><td>{}</td><td>{}{}</td></tr>".format(
            escape(item.path.name), escape(item.target), escape(item.kind),
            f" ({escape(item.transport.upper())})" if item.transport else "",
        )
        for item in artifacts
    )
    sections: list[str] = []
    desktop = [item for item in artifacts if item.target == "Claude Desktop"]
    if desktop:
        steps = ["Open <strong>Settings → Manage plugins → Add → Upload plugin</strong>."]
        steps += [
            f"Select <code>{escape(item.path.name)}</code> to install the skills."
            for item in desktop
            if item.kind == "skills plugin"
        ]
        extensions = [item for item in desktop if item.kind == "MCP extension"]
        if extensions:
            steps.append("Open <strong>Settings → Extensions → Install extension</strong>.")
            steps += [
                f"Select <code>{escape(item.path.name)}</code> ({escape(item.transport.upper())})."
                for item in extensions
            ]
        steps.append("Fully quit Claude Desktop, including its system-tray icon, then reopen it.")
        sections.append("<section><h2>Claude Desktop</h2><ol>" + "".join(
            f"<li>{step}</li>" for step in steps
        ) + "</ol></section>")

    claude_code = [item for item in artifacts if item.target == "Claude Code"]
    if claude_code:
        item = claude_code[0]
        body = f"<ol><li>Extract <code>{escape(item.path.name)}</code> to a folder.</li>"
        if item.plugin_name and item.marketplace_name:
            body += (
                "<li>In Claude Code, run:<pre><code>/plugin marketplace add "
                "&lt;absolute path to extracted folder&gt;\n/plugin install "
                f"{escape(item.plugin_name)}@{escape(item.marketplace_name)}"
                "</code></pre></li>"
            )
        else:
            body += "<li>Add the extracted folder through Claude Code’s Plugins screen.</li>"
        sections.append(f"<section><h2>Claude Code</h2>{body}</ol></section>")

    copilot = [item for item in artifacts if item.target == "GitHub Copilot"]
    if copilot:
        sections.append(
            "<section><h2>GitHub Copilot</h2><ol>"
            f"<li>Extract <code>{escape(copilot[0].path.name)}</code> to a folder.</li>"
            "<li>Open Copilot <strong>Settings → Plugins → Install Plugin from Source"
            "</strong>.</li>"
            "<li>Select the extracted folder, install the plugin, then reload the client.</li>"
            "</ol></section>"
        )

    codex = [item for item in artifacts if item.target == "Codex"]
    if codex:
        item = codex[0]
        body = f"<ol><li>Extract <code>{escape(item.path.name)}</code> to a folder.</li>"
        body += (
            "<li>In <strong>Codex Settings → Plugins</strong>, add the extracted folder "
            "as a marketplace.</li>"
        )
        if item.plugin_name and item.marketplace_name:
            body += (
                f"<li>Install <code>{escape(item.plugin_name)}@"
                f"{escape(item.marketplace_name)}</code> "
                "from that marketplace.</li>"
            )
        sections.append(f"<section><h2>Codex</h2>{body}</ol></section>")

    universal = _names(artifacts, "Universal")
    if universal:
        sections.append(
            "<section><h2>Universal archive</h2><p><code>"
            f"{escape(universal[0])}</code> is for storage or redistribution; it is not "
            "installed directly.</p></section>"
        )
    sections.append(
        "<section><h2>Verify</h2><ol><li>Restart the client completely.</li>"
        "<li>Confirm the package’s MCP tools and skills are visible.</li></ol></section>"
    )
    head = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Package installation guide</title>",
            "<style>",
            "body{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:40px auto;"
            "padding:0 20px;color:#18202a}",
            "h1,h2{color:#0b4f6c}table{border-collapse:collapse;width:100%}",
            "th,td{padding:9px;border:1px solid #d8e0e6;text-align:left}",
            "th{background:#eef6fa}code{background:#f3f5f7;padding:2px 4px;border-radius:3px}",
            "section{margin-top:28px}pre{padding:12px;background:#f3f5f7;overflow:auto}",
            "</style></head><body>",
        ]
    )
    table = (
        "<h2>Available packages</h2><table><thead><tr><th>File</th><th>Target</th>"
        f"<th>Type</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return "\n".join(
        [
            head,
            "<h1>Package installation guide</h1>",
            "<p>This guide is based only on the files in this folder.</p>",
            table,
            "\n".join(sections),
            "</body></html>",
            "",
        ]
    )


def write_guides(
    packages_dir: Path, output_dir: Path | None = None
) -> tuple[Path, Path, list[PackageArtifact]]:
    artifacts = scan(packages_dir)
    if not artifacts:
        raise AgentPackError(AP1003, f"no supported package artifacts found in: {packages_dir}")
    destination = (output_dir or packages_dir).resolve()
    markdown_path = destination / "INSTALL.md"
    html_path = destination / "INSTALL.html"
    write_text(markdown_path, render_markdown(artifacts))
    write_text(html_path, render_html(artifacts))
    return markdown_path, html_path, artifacts
