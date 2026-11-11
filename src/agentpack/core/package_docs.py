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
            members = archive.namelist()
            matched = member if member in members else next(
                (name for name in members if name.endswith(f"/{member}")), None
            )
            return json.loads(archive.read(matched).decode("utf-8")) if matched else {}
    except (KeyError, OSError, json.JSONDecodeError, zipfile.BadZipFile):
        return {}


def _plugin_identity(path: Path, member: str) -> tuple[str | None, str | None]:
    data = _zip_json(path, member)
    plugins = data.get("plugins") or []
    if not plugins:
        return None, None
    plugin = plugins[0]
    return plugin.get("name"), data.get("name")


def _has_name_part(name: str, part: str) -> bool:
    return name.startswith(f"{part}-") or f"-{part}-" in name


def scan(packages_dir: Path) -> list[PackageArtifact]:
    """Identify supported target artifacts without reading a project manifest."""
    packages_dir = packages_dir.resolve()
    if not packages_dir.is_dir():
        raise AgentPackError(AP1003, f"packages directory not found: {packages_dir}")

    artifacts: list[PackageArtifact] = []
    for path in sorted(packages_dir.iterdir(), key=lambda item: item.name.lower()):
        name = path.name.lower()
        if path.is_file() and _has_name_part(name, "claude-desktop") and name.endswith(".mcpb"):
            manifest = _zip_json(path, "manifest.json")
            command = ((manifest.get("server") or {}).get("mcp_config") or {}).get("command", "")
            transport = "http" if "bridge" in command or "-http-" in name else "stdio"
            artifacts.append(
                PackageArtifact(path, "Claude Desktop", "MCP extension", transport=transport)
            )
        elif path.is_file() and _has_name_part(name, "claude-desktop") and name.endswith(".plugin"):
            artifacts.append(PackageArtifact(path, "Claude Desktop", "skills plugin"))
        elif path.is_file() and _has_name_part(name, "claude-code") and name.endswith(".zip"):
            plugin, marketplace = _plugin_identity(path, ".claude-plugin/marketplace.json")
            artifacts.append(
                PackageArtifact(path, "Claude Code Cli", "plugin marketplace", plugin, marketplace)
            )
        elif path.is_file() and _has_name_part(name, "copilot-cli") and name.endswith(".zip"):
            manifest = _zip_json(path, "plugin.json")
            artifacts.append(
                PackageArtifact(path, "GitHub Copilot CLI", "plugin", manifest.get("name"))
            )
        elif path.is_file() and _has_name_part(name, "copilot") and name.endswith(".zip"):
            manifest = _zip_json(path, "plugin.json")
            artifacts.append(
                PackageArtifact(path, "VS Code GitHub Copilot", "plugin", manifest.get("name"))
            )
        elif path.is_file() and _has_name_part(name, "codex") and name.endswith(".zip"):
            plugin, marketplace = _plugin_identity(path, ".agents/plugins/marketplace.json")
            artifacts.append(
                PackageArtifact(path, "Codex", "plugin marketplace", plugin, marketplace)
            )
        elif path.is_file() and _has_name_part(name, "universal") and name.endswith(".zip"):
            artifacts.append(PackageArtifact(path, "Universal", "archive"))
    return artifacts


def _names(artifacts: list[PackageArtifact], target: str) -> list[str]:
    return [artifact.path.name for artifact in artifacts if artifact.target == target]


def _platform(item: PackageArtifact) -> str | None:
    name = item.path.name.lower()
    if "-win-" in name or "-windows-" in name:
        return "Windows"
    if "-linux-" in name:
        return "Linux"
    return None


CLAUDE_DESKTOP_CONNECTORS_STEP = (
    "Open **Settings → Customize → Connectors**, choose **Your Connectors**, and change "
    "the connector permission from **Needs Approval** to **Always allow**. Otherwise, "
    "Claude Desktop asks you to confirm every action the connector performs."
)

CLAUDE_DESKTOP_CONNECTORS_STEP_HTML = (
    "Open <strong>Settings → Customize → Connectors</strong>, choose "
    "<strong>Your Connectors</strong>, and change the connector permission from "
    "<strong>Needs Approval</strong> to <strong>Always allow</strong>. Otherwise, "
    "Claude Desktop asks you to confirm every action the connector performs."
)


def _copilot_app_install_link(item: PackageArtifact) -> str:
    name = item.plugin_name or "<plugin-name>"
    return f"ghapp://plugins/install?source={name}%40{name}"


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
        lines.append(f"5. {CLAUDE_DESKTOP_CONNECTORS_STEP}")
        lines.append(
            "6. Fully quit Claude Desktop, including its system-tray icon, then reopen it."
        )

    claude_code = [item for item in artifacts if item.target in ("Claude Code", "Claude Code Cli")]
    if claude_code:
        lines += ["", "## Claude Code Cli", ""]
        for item in claude_code:
            platform = _platform(item)
            if platform:
                lines += [f"### {platform}", ""]
            lines += [
                f"1. Extract `{item.path.name}` into a versioned folder.",
                "2. For a first install, register the folder as a local marketplace and install "
                "the plugin:",
                "",
                "```bash",
                "claude plugin marketplace add \"<absolute path to extracted folder>\"",
            ]
            if item.plugin_name and item.marketplace_name:
                lines += [
                    f"claude plugin install {item.plugin_name}@"
                    f"{item.marketplace_name} --scope user",
                    "```",
                    "",
                    "3. To update an existing install, keep using the same marketplace folder, "
                    "put the new build there, then refresh and update it:",
                    "",
                    "```bash",
                    f"claude plugin marketplace update {item.marketplace_name}",
                    f"claude plugin update {item.plugin_name}@{item.marketplace_name}",
                    "claude plugin list",
                    "```",
                ]
            else:
                lines += [
                    "```",
                    "",
                    "3. Install or update the plugin from the registered marketplace in Claude "
                    "Code.",
                ]
            lines += [
                "",
                "To test a new build from a different folder without replacing the installed "
                "plugin, start a one-off session with "
                "`claude --plugin-dir \"<absolute path to extracted plugin folder>\"`.",
                "",
            ]

    copilot = [
        item for item in artifacts if item.target in ("GitHub Copilot", "VS Code GitHub Copilot")
    ]
    if copilot:
        lines += [
            "",
            "## VS Code GitHub Copilot",
            "",
            f"1. Extract `{copilot[0].path.name}` to a folder.",
            "2. Open Copilot **Settings → Plugins → Install Plugin from Source**.",
            "3. Select the extracted folder, install the plugin, then reload the client.",
        ]

    copilot_cli = [item for item in artifacts if item.target == "GitHub Copilot CLI"]
    if copilot_cli:
        lines += [
            "",
            "## GitHub Copilot CLI",
            "",
        ]
        for item in copilot_cli:
            platform = _platform(item)
            if platform:
                label = "Windows (PowerShell)" if platform == "Windows" else "Linux (Bash)"
                lines += [f"### {label}", ""]
                plugin_name = item.plugin_name or "<plugin-name>"
                lines += [
                    f"1. Extract `{item.path.name}` to a versioned folder; use the folder "
                    "containing `plugin.json`.",
                    "2. First install: run `copilot plugin install "
                    "\"<absolute path to plugin folder>\"`.",
                    f"3. To update the installed `{plugin_name}`, replace all files in the "
                    "same source folder with the new build, then run "
                    f"`copilot plugin update {plugin_name}`.",
                    "4. Run `copilot plugin list` to verify the version, then exit Copilot CLI "
                    "completely and run `copilot` again to start a fresh MCP server process.",
                    "",
                ]
                if platform == "Windows":
                    lines += [
                        "To test a different extracted folder without changing the default "
                        "profile, use a separate config directory in the same PowerShell session:",
                        "",
                        "```powershell",
                        '$env:COPILOT_HOME = "$HOME\\.copilot-plugin-test"',
                        'copilot plugin install "<absolute path to test plugin folder>"',
                        "copilot plugin list",
                        "copilot",
                        "```",
                        "",
                        "Close that terminal to return to the default profile.",
                        "",
                    ]
                else:
                    lines += [
                        "To test a different extracted folder without changing the default "
                        "profile, use a separate config directory in the same Bash session:",
                        "",
                        "```bash",
                        'export COPILOT_HOME="$HOME/.copilot-plugin-test"',
                        'copilot plugin install "<absolute path to test plugin folder>"',
                        "copilot plugin list",
                        "copilot",
                        "```",
                        "",
                        "Close that terminal or unset `COPILOT_HOME` to return to the default "
                        "profile.",
                        "",
                    ]
            else:
                plugin_name = item.plugin_name or "<plugin-name>"
                lines += [
                    f"1. Extract `{item.path.name}` into a folder containing `plugin.json`.",
                    "2. Install with `copilot plugin install <absolute path to plugin folder>`.",
                    "3. To update the existing install, replace all contents of its source "
                    f"folder and run `copilot plugin update {plugin_name}`.",
                    "4. Run `copilot plugin list`, then exit Copilot CLI completely and run "
                    "`copilot` again to start a fresh MCP server process.",
                    "",
                ]

        win_item = next(
            (item for item in copilot_cli if _platform(item) == "Windows"),
            copilot_cli[0],
        )
        if win_item:
            app_install_link = _copilot_app_install_link(win_item)
            lines += [
                "### GitHub Copilot App (UI)",
                "",
                f"1. Extract `{win_item.path.name}` to a folder.",
                "2. In the GitHub Copilot App, open **Customize**.",
                "3. Select the **Installed** tab.",
                "4. Click the **+ Add Plugin** button and choose **Manage Marketplaces**.",
                "5. Paste the extracted plugin directory path into the **Source** field and press "
                "**Add**.",
                "6. If there is no install option, run the following command in PowerShell "
                "(Windows):",
                "",
                "```powershell",
                f"Start-Process '{app_install_link}'",
                "```",
                "",
                "7. In the app panel, press **Allow**, then press **Install**.",
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
        steps.append(CLAUDE_DESKTOP_CONNECTORS_STEP_HTML)
        steps.append("Fully quit Claude Desktop, including its system-tray icon, then reopen it.")
        sections.append("<section><h2>Claude Desktop</h2><ol>" + "".join(
            f"<li>{step}</li>" for step in steps
        ) + "</ol></section>")

    claude_code = [item for item in artifacts if item.target in ("Claude Code", "Claude Code Cli")]
    if claude_code:
        bodies = []
        for item in claude_code:
            platform = _platform(item)
            heading = f"<h3>{escape(platform)}</h3>" if platform else ""
            body = (
                f"{heading}<ol><li>Extract <code>{escape(item.path.name)}</code> into a "
                "versioned folder.</li>"
            )
            if item.plugin_name and item.marketplace_name:
                body += (
                    "<li>For a first install, register the folder as a local marketplace and "
                    "install the plugin:<pre><code>claude plugin marketplace add "
                    "&quot;&lt;absolute path to extracted folder&gt;&quot;\n"
                    f"claude plugin install {escape(item.plugin_name)}@"
                    f"{escape(item.marketplace_name)} --scope user</code></pre></li>"
                    "<li>For an update, replace the files at the same marketplace path, "
                    "then run:<pre><code>"
                    f"claude plugin marketplace update {escape(item.marketplace_name)}\n"
                    f"claude plugin update {escape(item.plugin_name)}@"
                    f"{escape(item.marketplace_name)}\nclaude plugin list</code></pre></li>"
                )
            else:
                body += (
                    "<li>Install or update the plugin from the registered marketplace in "
                    "Claude Code.</li>"
                )
            body += (
                "<li>To test a new build from a different folder without replacing the "
                "installed plugin, start a one-off session with "
                "<code>claude --plugin-dir &quot;&lt;absolute path to extracted plugin "
                "folder&gt;&quot;</code>.</li></ol>"
            )
            bodies.append(body)
        sections.append(
            "<section><h2>Claude Code Cli</h2>" + "".join(bodies) + "</section>"
        )

    copilot = [
        item for item in artifacts if item.target in ("GitHub Copilot", "VS Code GitHub Copilot")
    ]
    if copilot:
        sections.append(
            "<section><h2>VS Code GitHub Copilot</h2><ol>"
            f"<li>Extract <code>{escape(copilot[0].path.name)}</code> to a folder.</li>"
            "<li>Open Copilot <strong>Settings → Plugins → Install Plugin from Source"
            "</strong>.</li>"
            "<li>Select the extracted folder, install the plugin, then reload the client.</li>"
            "</ol></section>"
        )

    copilot_cli = [item for item in artifacts if item.target == "GitHub Copilot CLI"]
    if copilot_cli:
        bodies = []
        for item in copilot_cli:
            platform = _platform(item)
            plugin_name = escape(item.plugin_name or "<plugin-name>")
            name = escape(item.path.name)
            if platform == "Windows":
                body = (
                    "<h3>Windows (PowerShell)</h3><ol>"
                    f"<li>Extract <code>{name}</code> to a versioned folder; use the folder "
                    "that contains <code>plugin.json</code>.</li>"
                    "<li>First install: <code>copilot plugin install &quot;&lt;absolute path "
                    "to plugin folder&gt;&quot;</code>.</li>"
                    f"<li>To update <code>{plugin_name}</code>, replace all files in the "
                    "same source folder, then run "
                    f"<code>copilot plugin update {plugin_name}</code>.</li>"
                    "<li>Run <code>copilot plugin list</code> to verify the version, then exit "
                    "Copilot CLI completely and run <code>copilot</code> again to start a fresh "
                    "MCP server process.</li></ol>"
                    "<p>To test a different folder without changing the default profile, "
                    "use a separate config directory in the same PowerShell session:</p>"
                    '<pre><code>$env:COPILOT_HOME = "$HOME\\.copilot-plugin-test"\n'
                    'copilot plugin install "&lt;absolute path to test plugin folder&gt;"\n'
                    "copilot plugin list\ncopilot</code></pre>"
                    "<p>Close that terminal to return to the default profile.</p>"
                )
            elif platform == "Linux":
                body = (
                    "<h3>Linux (Bash)</h3><ol>"
                    f"<li>Extract <code>{name}</code> to a versioned folder; use the folder "
                    "that contains <code>plugin.json</code>.</li>"
                    "<li>First install: <code>copilot plugin install &quot;&lt;absolute path "
                    "to plugin folder&gt;&quot;</code>.</li>"
                    f"<li>To update <code>{plugin_name}</code>, replace all files in the "
                    "same source folder, then run "
                    f"<code>copilot plugin update {plugin_name}</code>.</li>"
                    "<li>Run <code>copilot plugin list</code> to verify the version, then exit "
                    "Copilot CLI completely and run <code>copilot</code> again to start a fresh "
                    "MCP server process.</li></ol>"
                    "<p>To test a different folder without changing the default profile, "
                    "use a separate config directory in the same Bash session:</p>"
                    '<pre><code>export COPILOT_HOME="$HOME/.copilot-plugin-test"\n'
                    'copilot plugin install "&lt;absolute path to test plugin folder&gt;"\n'
                    "copilot plugin list\ncopilot</code></pre>"
                    "<p>Close that terminal or unset <code>COPILOT_HOME</code> to return "
                    "to the default profile.</p>"
                )
            else:
                body = (
                    f"<h3>Install from <code>{name}</code></h3><ol>"
                    "<li>Extract it to a folder containing <code>plugin.json</code>.</li>"
                    "<li>Install with <code>copilot plugin install &lt;absolute path to "
                    "plugin folder&gt;</code>.</li>"
                    f"<li>Update with <code>copilot plugin update {plugin_name}</code>, "
                    "then verify using <code>copilot plugin list</code>.</li></ol>"
                )
            bodies.append(body)
        sections.append(
            "<section><h2>GitHub Copilot CLI</h2>" + "".join(bodies) + "</section>"
        )

        win_item = next(
            (item for item in copilot_cli if _platform(item) == "Windows"),
            copilot_cli[0],
        )
        if win_item:
            win_zip = escape(win_item.path.name)
            app_install_link = escape(_copilot_app_install_link(win_item))
            sections.append(
                "<section><h2>GitHub Copilot App (UI)</h2><ol>"
                f"<li>Extract <code>{win_zip}</code> to a folder.</li>"
                "<li>In the GitHub Copilot App, open <strong>Customize</strong>.</li>"
                "<li>Select the <strong>Installed</strong> tab.</li>"
                "<li>Click the <strong>+ Add Plugin</strong> button and choose "
                "<strong>Manage Marketplaces</strong>.</li>"
                "<li>Paste the extracted plugin directory path into the "
                "<strong>Source</strong> field and press <strong>Add</strong>.</li>"
                "<li>If there is no install option, run this in PowerShell "
                "(Windows):<pre><code>"
                f"Start-Process '{app_install_link}'"
                "</code></pre></li>"
                "<li>In the app panel, press <strong>Allow</strong>, then press "
                "<strong>Install</strong>.</li></ol></section>"
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
    packages_dir: Path, output_dir: Path | None = None, name_suffix: str | None = None
) -> tuple[Path, Path, list[PackageArtifact]]:
    artifacts = scan(packages_dir)
    if not artifacts:
        raise AgentPackError(AP1003, f"no supported package artifacts found in: {packages_dir}")
    destination = (output_dir or packages_dir).resolve()
    filename = f"INSTALL-{name_suffix}" if name_suffix else "INSTALL"
    markdown_path = destination / f"{filename}.md"
    html_path = destination / f"{filename}.html"
    write_text(markdown_path, render_markdown(artifacts))
    write_text(html_path, render_html(artifacts))
    return markdown_path, html_path, artifacts
