from __future__ import annotations

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from agentpack.cli import app


def _zip(path: Path, member: str, data: dict) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, json.dumps(data))


def test_target_install_writes_guides_from_package_files_only(tmp_path: Path):
    packages = tmp_path / "packages"
    packages.mkdir()
    _zip(
        packages / "claude-code-1.2.3.zip",
        ".claude-plugin/marketplace.json",
        {"name": "demo-marketplace", "plugins": [{"name": "demo-plugin"}]},
    )
    _zip(
        packages / "codex-marketplace-1.2.3.zip",
        ".agents/plugins/marketplace.json",
        {"name": "demo-marketplace", "plugins": [{"name": "demo-plugin"}]},
    )
    _zip(packages / "copilot-1.2.3.zip", "plugin.json", {"name": "demo-plugin"})
    _zip(packages / "copilot-cli-stdio-1.2.3.zip", "plugin.json", {"name": "demo-cli"})
    _zip(packages / "universal-1.2.3.zip", "plugin.json", {})
    _zip(
        packages / "claude-desktop-demo-http-1.2.3.mcpb",
        "manifest.json",
        {"server": {"mcp_config": {"command": "bridge.exe"}}},
    )
    (packages / "claude-desktop-cowork-plugin-1.2.3.plugin").write_bytes(b"plugin")

    result = CliRunner().invoke(app, ["target-install", str(packages)])
    assert result.exit_code == 0, result.output
    markdown = (packages / "INSTALL.md").read_text(encoding="utf-8")
    html = (packages / "INSTALL.html").read_text(encoding="utf-8")
    assert "demo-plugin@demo-marketplace" in markdown
    assert "MCP extension (HTTP)" in markdown
    assert "Settings → Customize → Connectors" in markdown
    assert "Needs Approval" in markdown
    assert "Always allow" in markdown
    assert "GitHub Copilot CLI" in markdown
    assert "copilot plugin install" in markdown
    assert "copilot plugin uninstall <old-plugin>" in markdown
    assert "plugin directory is in use" in markdown
    assert "## Claude Code Cli" in markdown
    assert "## VS Code GitHub Copilot" in markdown
    assert "## GitHub Copilot CLI" in markdown
    assert "### GitHub Copilot App (UI)" in markdown
    assert "agentpack" not in markdown.lower()
    assert html.count("<h2>Available packages</h2>") == 1
    assert "demo-plugin@demo-marketplace" in html
    assert "Settings → Customize → Connectors" in html
    assert "<h2>Claude Code Cli</h2>" in html
    assert "<h2>VS Code GitHub Copilot</h2>" in html
    assert "<h2>GitHub Copilot CLI</h2>" in html
    assert "<h2>GitHub Copilot App (UI)</h2>" in html
    assert "copilot plugin uninstall &lt;old-plugin&gt;" in html
    assert "plugin directory is in use" in html
    assert "GitHub Copilot App (UI)" in html
    assert "Customize" in html
    assert "Installed" in html
    assert "+ Add Plugin" in html
    assert "Manage Marketplaces" in html
    assert "Source" in html


def test_docs_command_updates_guides(tmp_path: Path):
    packages = tmp_path / "packages"
    packages.mkdir()
    _zip(packages / "copilot-cli-stdio-1.0.0.zip", "plugin.json", {"name": "demo-cli"})

    result = CliRunner().invoke(app, ["docs", str(packages)])
    assert result.exit_code == 0, result.output
    assert (packages / "INSTALL.md").is_file()
    assert (packages / "INSTALL.html").is_file()

    result_alias = CliRunner().invoke(app, ["update-docs", str(packages)])
    assert result_alias.exit_code == 0, result_alias.output
