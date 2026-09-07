from __future__ import annotations

import json
from pathlib import Path

from agentpack.core.builder import build
from agentpack.core.diagnostics import Diagnostics
from agentpack.core.loader import load_package

ALL_TARGETS = ["universal", "claude-desktop", "copilot", "codex"]


def _guide(package, tmp_path: Path, **kw) -> tuple[Path, str]:
    summary = build(package, targets=ALL_TARGETS, output_dir=tmp_path / "dist", **kw)
    assert summary.install_guide_path is not None
    return summary.install_guide_path, summary.install_guide_path.read_text(encoding="utf-8")


def test_install_guide_is_written_next_to_the_build_manifest(package, tmp_path: Path):
    path, text = _guide(package, tmp_path)
    assert path == tmp_path / "dist" / "INSTALL.md"
    assert text.startswith("# Installing Network Operations Toolkit 0.1.0")


def test_install_guide_lists_every_target(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    for target in ALL_TARGETS:
        assert f"## {target}" in text


def test_install_guide_lists_archive_filenames(package, tmp_path: Path):
    _, text = _guide(package, tmp_path, archive=True)
    assert "packages/claude-desktop-netops-stdio-0.1.0.mcpb" in text
    assert "packages/codex-marketplace-mixed-0.1.0.zip" in text


def test_install_guide_falls_back_to_directories_without_archives(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    table = text.split("## Artifacts")[1].split("##")[0]
    assert "| `build/codex/` |" in table
    assert ".zip" not in table


def test_install_guide_states_the_no_manual_copy_rule(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    assert "skills are never installed one by one" in text


def test_codex_install_guide_explains_how_to_replace_an_old_plugin(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    assert "Adding a marketplace only makes its plugin available" in text
    assert "codex plugin add network-operations@network-operations-marketplace" in text
    assert "codex plugin remove <old-plugin>@<old-marketplace>" in text
    assert "MONITORING_TOKEN" in text
    assert "<token-without-Bearer>" in text


def test_install_guide_lists_required_values_without_secrets(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    assert "| netops | `NETOPS_TOKEN` | yes | yes |" in text
    assert "never embedded" in text


def test_build_manifest_points_at_the_guide(package, tmp_path: Path):
    build(package, targets=["universal"], output_dir=tmp_path / "dist")
    manifest = json.loads(
        (tmp_path / "dist" / "agentpack-build.json").read_text(encoding="utf-8")
    )
    assert manifest["installGuide"] == "INSTALL.md"


def test_package_writes_standalone_guides_next_to_archives(package, tmp_path: Path):
    build(package, targets=ALL_TARGETS, output_dir=tmp_path / "dist", archive=True)
    packages = tmp_path / "dist" / "packages"
    markdown = (packages / "INSTALL-mixed-0.1.0.md").read_text(encoding="utf-8")
    assert (packages / "INSTALL-mixed-0.1.0.html").is_file()
    assert "claude-desktop-netops-stdio-0.1.0.mcpb" in markdown
    assert "Settings → Customize → Connectors" in markdown
    assert "Always allow" in markdown
    assert "agentpack" not in markdown.lower()


def test_package_guide_filename_includes_http_host(project, tmp_path: Path):
    package = load_package(project, Diagnostics())
    http_server = next(server for server in package.mcp_servers if server.is_remote)
    assert http_server.endpoint is not None
    http_server.endpoint.url = "http://172.18.178.24/mcp"
    package.mcp_servers = [http_server]
    package.metadata.version = "0.27.0"

    build(package, targets=["copilot"], output_dir=tmp_path / "dist", archive=True)

    packages = tmp_path / "dist" / "packages"
    assert (packages / "INSTALL-http-172.18.178.24-0.27.0.md").is_file()
    assert (packages / "INSTALL-http-172.18.178.24-0.27.0.html").is_file()


def test_install_guide_includes_claude_desktop_connector_permission(package, tmp_path: Path):
    _, text = _guide(package, tmp_path)
    assert "Settings → Customize → Connectors" in text
    assert "Needs Approval" in text
    assert "Always allow" in text
