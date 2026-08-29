from __future__ import annotations

import json
from pathlib import Path

from agentpack.core.builder import build
from agentpack.models.package import KnowledgeMode

ALL_TARGETS = [
    "universal",
    "claude-desktop",
    "claude-code",
    "copilot-vscode",
    "copilot-intellij",
    "codex",
]


def _build(package, tmp_path: Path, **kw):
    return build(package, targets=ALL_TARGETS, output_dir=tmp_path / "dist", **kw)


def test_builds_every_target(package, tmp_path: Path):
    summary = _build(package, tmp_path)
    assert summary.ok
    assert {r.target for r in summary.results} == set(ALL_TARGETS)
    manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert manifest["packageVersion"] == "0.1.0"
    assert len(manifest["artifacts"]) == len(ALL_TARGETS)


def test_build_is_deterministic(package, tmp_path: Path):
    first = _build(package, tmp_path / "a")
    second = _build(package, tmp_path / "b")
    digests = {
        (a["target"], a["sha256"]) for a in json.loads(first.manifest_path.read_text())["artifacts"]
    }
    other = {
        (a["target"], a["sha256"])
        for a in json.loads(second.manifest_path.read_text())["artifacts"]
    }
    assert digests == other


def test_copilot_vscode_uses_servers_key_and_inputs(package, tmp_path: Path):
    _build(package, tmp_path)
    config = json.loads(
        (tmp_path / "dist" / "build" / "copilot-vscode" / "mcp.json").read_text(encoding="utf-8")
    )
    assert "servers" in config and "mcpServers" not in config
    ids = {i["id"] for i in config["inputs"]}
    assert "netops-netops-token" in ids
    assert config["servers"]["netops"]["env"]["NETOPS_TOKEN"] == "${input:netops-netops-token}"
    assert config["servers"]["netops"]["env"]["NETOPS_READONLY"] == "true"
    assert all(i["password"] is not None for i in config["inputs"])


def test_no_secret_value_leaks_into_any_artifact(package, tmp_path: Path):
    package.mcp_servers[1].environment["NETOPS_TOKEN"].description = "token"
    _build(package, tmp_path)
    for path in (tmp_path / "dist").rglob("*"):
        if path.is_file() and path.suffix in {".json", ".toml", ".md", ".yaml"}:
            assert "supersecret" not in path.read_text(encoding="utf-8", errors="ignore")


def test_claude_desktop_manifest_shape(package, tmp_path: Path):
    _build(package, tmp_path)
    bundle = (
        tmp_path / "dist" / "build" / "claude-desktop" / "mcpb" / "netops" / "manifest.json"
    )
    manifest = json.loads(bundle.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "0.3"
    assert manifest["name"] == "network-operations-netops"
    assert manifest["server"]["type"] == "python"
    assert manifest["server"]["entry_point"] == "netops_mcp.server"
    assert manifest["server"]["mcp_config"]["env"]["NETOPS_TOKEN"] == "${user_config.netops_token}"
    assert manifest["user_config"]["netops_token"]["sensitive"] is True
    assert "default" not in manifest["user_config"]["netops_token"]


def test_claude_desktop_ships_skills_as_one_plugin(package, tmp_path: Path):
    _build(package, tmp_path)
    plugin = tmp_path / "dist" / "build" / "claude-desktop" / "plugin" / "network-operations"
    assert (plugin / ".claude-plugin" / "plugin.json").is_file()
    assert (plugin / "skills" / "network-analysis" / "SKILL.md").is_file()
    assert (plugin / "skills" / "incident-report" / "SKILL.md").is_file()
    # No loose skills tree to copy by hand.
    assert not (tmp_path / "dist" / "build" / "claude-desktop" / "skills").exists()


def test_claude_desktop_bridges_remote_server_with_mcp_remote(package, tmp_path: Path):
    _build(package, tmp_path)
    manifest = json.loads(
        (
            tmp_path / "dist" / "build" / "claude-desktop" / "mcpb" / "monitoring" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    config = manifest["server"]["mcp_config"]
    assert manifest["server"]["type"] == "node"
    assert config["command"] == "npx"
    assert config["args"][:3] == ["-y", "mcp-remote", "https://mcp.example.com/mcp"]
    assert "--header" in config["args"]
    assert "Authorization: ${user_config.authorization}" in config["args"]
    assert manifest["user_config"]["authorization"]["sensitive"] is True


def test_claude_code_uses_mcpservers_key(package, tmp_path: Path):
    _build(package, tmp_path)
    config = json.loads(
        (
            tmp_path / "dist" / "build" / "claude-code" / "network-operations" / ".mcp.json"
        ).read_text(encoding="utf-8")
    )
    assert "mcpServers" in config
    assert config["monitoring"]["url"] if "monitoring" in config else True
    assert config["mcpServers"]["monitoring"]["url"] == "https://mcp.example.com/mcp"


def test_codex_emits_toml_tables(package, tmp_path: Path):
    _build(package, tmp_path)
    toml = (tmp_path / "dist" / "build" / "codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.netops]" in toml
    assert 'type = "local"' in toml
    assert "[mcp_servers.netops.env]" in toml
    assert "bearer_token_env_var" in toml


def test_served_mode_strips_references_and_stamps(package, tmp_path: Path):
    package.build.knowledge = KnowledgeMode.SERVED
    _build(package, tmp_path)
    skill_dir = tmp_path / "dist" / "build" / "universal" / "skills" / "network-analysis"
    assert not (skill_dir / "references").exists()
    assert "<!--agentpack-mode:served-->" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")


def test_bundled_mode_keeps_references(package, tmp_path: Path):
    _build(package, tmp_path)
    skill_dir = tmp_path / "dist" / "build" / "universal" / "skills" / "network-analysis"
    assert (skill_dir / "references" / "alarms.md").is_file()
    assert "<!--agentpack-mode:served-->" not in (skill_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_strict_mode_fails_on_warnings(package, tmp_path: Path):
    summary = _build(package, tmp_path, strict=True)
    assert summary.diagnostics.warnings
    assert not summary.results


def test_every_archive_names_package_target_and_version(package, tmp_path: Path):
    summary = _build(package, tmp_path, archive=True)
    for result in summary.results:
        assert result.archives, f"{result.target} produced no archive"
        for path in result.archives:
            assert path.name.startswith(f"network-operations-{result.target}-")
            assert path.stem.endswith("0.1.0")


def test_claude_desktop_archives_are_split_per_server_plus_skills(package, tmp_path: Path):
    summary = _build(package, tmp_path, archive=True)
    claude = next(r for r in summary.results if r.target == "claude-desktop")
    assert sorted(p.name for p in claude.archives) == [
        "network-operations-claude-desktop-monitoring-0.1.0.mcpb",
        "network-operations-claude-desktop-netops-0.1.0.mcpb",
        "network-operations-claude-desktop-skills-0.1.0.zip",
    ]


def test_readmes_forbid_manual_copying(package, tmp_path: Path):
    summary = _build(package, tmp_path)
    for result in summary.results:
        readme = (result.output_dir / "README.md").read_text(encoding="utf-8")
        assert "skills are never installed one by one" in readme


def test_every_target_emits_a_readme(package, tmp_path: Path):
    summary = _build(package, tmp_path)
    for result in summary.results:
        assert (result.output_dir / "README.md").is_file()
