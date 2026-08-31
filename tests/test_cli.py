from __future__ import annotations

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from agentpack.cli import app

runner = CliRunner()

MANIFEST = """apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage
metadata:
  name: custom
  version: 3.2.1
  description: Hand written manifest.
targets: [universal]
skills:
  - path: my-skills/
mcp:
  - path: servers/alpha.yaml
"""

SKILL = """---
name: alpha
description: Alpha skill.
version: 1.0.0
---

# Alpha
"""

MCP = """apiVersion: agentpack.dev/v1alpha1
kind: MCPServer
metadata:
  name: alpha
transport:
  type: stdio
command:
  executable: python
  args: ["-m", "alpha.server"]
"""


def make_project(root: Path, manifest_name: str = "agentpack.yaml") -> Path:
    """A project whose paths are relative to the manifest, not to the CWD."""
    (root / "my-skills" / "alpha").mkdir(parents=True)
    (root / "servers").mkdir(parents=True)
    (root / manifest_name).write_text(MANIFEST, encoding="utf-8")
    (root / "my-skills" / "alpha" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (root / "servers" / "alpha.yaml").write_text(MCP, encoding="utf-8")
    return root / manifest_name


def test_validate_accepts_a_manifest_file(tmp_path: Path):
    manifest = make_project(tmp_path / "proj")
    result = runner.invoke(app, ["validate", "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "1 skill(s), 1 MCP server(s)" in result.output


def test_manifest_may_have_any_filename(tmp_path: Path):
    manifest = make_project(tmp_path / "proj", "netops.agentpack.yaml")
    result = runner.invoke(app, ["validate", "-f", str(manifest)])
    assert result.exit_code == 0, result.output


def test_paths_resolve_relative_to_the_manifest_not_the_cwd(tmp_path: Path, monkeypatch):
    manifest = make_project(tmp_path / "proj")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(app, ["inspect", "-f", str(manifest), "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["metadata"]["name"] == "custom"
    assert [s["name"] for s in data["skills"]] == ["alpha"]
    assert data["project_dir"].replace("\\", "/").endswith("proj")


def test_package_writes_dist_next_to_the_manifest(tmp_path: Path, monkeypatch):
    manifest = make_project(tmp_path / "proj")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["package", "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "proj" / "dist" / "packages" / "universal-3.2.1.zip").is_file()
    assert not (tmp_path / "dist").exists()


def test_build_output_option_still_wins(tmp_path: Path):
    manifest = make_project(tmp_path / "proj")
    out = tmp_path / "somewhere-else"
    result = runner.invoke(app, ["build", "-f", str(manifest), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "build" / "universal" / "plugin.json").is_file()


def test_missing_manifest_file_exits_cleanly(tmp_path: Path):
    result = runner.invoke(app, ["validate", "-f", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert "AP1001" in result.output


def test_project_option_still_works(tmp_path: Path):
    make_project(tmp_path / "proj")
    result = runner.invoke(app, ["validate", "-p", str(tmp_path / "proj")])
    assert result.exit_code == 0, result.output


def test_pack_import_copies_portable_runtime_skills_and_mcp(tmp_path: Path):
    project = tmp_path / "project"
    result = runner.invoke(app, ["init", str(project), "--name", "portable-test"])
    assert result.exit_code == 0, result.output

    source = tmp_path / "producer-pack"
    (source / "skills" / "network").mkdir(parents=True)
    (source / "mcps").mkdir()
    (source / "runtime" / "windows-amd64").mkdir(parents=True)
    (source / "config").mkdir()
    (source / "skills" / "network" / "SKILL.md").write_text(
        SKILL.replace("name: alpha", "name: network"), encoding="utf-8"
    )
    (source / "runtime" / "windows-amd64" / "server.exe").write_bytes(b"runtime")
    (source / "config" / "inventory.example.yaml").write_text("devices: []\n")
    (source / "mcps" / "stdio.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "rad-network-toolkit": {
                        "type": "stdio",
                        "command": "${packageRoot}/runtime/windows-amd64/server.exe",
                        "args": ["--server", "legacy"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (source / "pack.json").write_text(
        json.dumps(
            {
                "portable": True,
                "runtime": "windows-amd64",
                "knowledge": "served",
                "mcps": ["stdio.json"],
                "package_root_placeholder": "${packageRoot}",
                "mutable_config": "%LOCALAPPDATA%\\RAD",
            }
        ),
        encoding="utf-8",
    )

    imported = runner.invoke(
        app, ["pack", "import", str(source), "--project", str(project)]
    )
    assert imported.exit_code == 0, imported.output
    assert "Skills: 1; MCP servers: 1" in imported.output
    assert (project / "portable" / "runtime" / "windows-amd64" / "server.exe").is_file()

    built = runner.invoke(
        app, ["build", "--project", str(project), "--target", "claude-desktop"]
    )
    assert built.exit_code == 0, built.output
    bundle = project / "dist" / "build" / "claude-desktop" / "mcpb" / "rad-network-toolkit"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["server"]["mcp_config"]["command"] == (
        "${__dirname}/runtime/windows-amd64/server.exe"
    )
    assert (bundle / "runtime" / "windows-amd64" / "server.exe").is_file()

    all_targets = runner.invoke(app, ["build", "--project", str(project)])
    assert all_targets.exit_code == 0, all_targets.output
    build_root = project / "dist" / "build"
    claude_code = json.loads(
        (build_root / "claude-code" / "portable-test" / ".mcp.json").read_text()
    )
    copilot = json.loads((build_root / "copilot" / ".mcp.json").read_text())
    codex = json.loads(
        (build_root / "codex" / "plugins" / "portable-test" / ".mcp.json").read_text()
    )
    for config in (claude_code, copilot, codex):
        command = config["mcpServers"]["rad-network-toolkit"]["command"]
        assert command == "${CLAUDE_PLUGIN_ROOT}/runtime/windows-amd64/server.exe"
    assert (build_root / "universal" / "runtime" / "windows-amd64" / "server.exe").is_file()

    packaged = runner.invoke(
        app, ["package", "--project", str(project), "--target", "claude-desktop"]
    )
    assert packaged.exit_code == 0, packaged.output
    mcpb = project / "dist" / "packages" / (
        "claude-desktop-rad-network-toolkit-stdio-0.1.0.mcpb"
    )
    assert mcpb.is_file()
    with zipfile.ZipFile(mcpb) as archive:
        assert "runtime/windows-amd64/server.exe" in archive.namelist()
