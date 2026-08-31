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
    assert "agentpack" not in markdown.lower()
    assert html.count("<h2>Available packages</h2>") == 1
    assert "demo-plugin@demo-marketplace" in html
