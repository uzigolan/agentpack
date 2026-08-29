from __future__ import annotations

import json
from pathlib import Path

from agentpack.core.builder import build

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
    assert "packages/network-operations-claude-desktop-netops-0.1.0.mcpb" in text
    assert "packages/network-operations-codex-marketplace-0.1.0.zip" in text


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
