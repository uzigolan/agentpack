from __future__ import annotations

import json
from pathlib import Path

from agentpack.core.builder import build
from agentpack.models.package import BuildOptions, EnvVarSource, KnowledgeMode

ALL_TARGETS = [
    "universal",
    "claude-desktop",
    "claude-code",
    "copilot",
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


def test_copilot_plugin_has_a_manifest_and_mcp_config(package, tmp_path: Path):
    _build(package, tmp_path)
    config = json.loads(
        (tmp_path / "dist" / "build" / "copilot" / "mcp.json").read_text(encoding="utf-8")
    )
    assert "servers" in config and "mcpServers" not in config
    ids = {i["id"] for i in config["inputs"]}
    assert "netops-netops-token" in ids
    assert config["servers"]["netops"]["env"]["NETOPS_TOKEN"] == "${input:netops-netops-token}"
    assert config["servers"]["netops"]["env"]["NETOPS_READONLY"] == "true"
    assert (
        config["servers"]["monitoring"]["headers"]["Authorization"]
        == "Bearer ${input:monitoring-authorization}"
    )
    assert all(i["password"] is not None for i in config["inputs"])
    root_plugin = json.loads((tmp_path / "dist" / "build" / "copilot" / "plugin.json").read_text())
    assert root_plugin["mcpServers"] == ".mcp.json"
    assert root_plugin["skills"] == ["skills/"]
    plugin = tmp_path / "dist" / "build" / "copilot" / ".copilot-plugin" / "plugin.json"
    assert json.loads(plugin.read_text(encoding="utf-8"))["name"] == "network-operations"
    assert (plugin.parents[1] / ".claude-plugin" / "plugin.json").is_file()
    plugin_mcp = json.loads((plugin.parents[1] / ".mcp.json").read_text(encoding="utf-8"))
    assert "mcpServers" in plugin_mcp


def test_no_secret_value_leaks_into_any_artifact(package, tmp_path: Path):
    package.mcp_servers[1].environment["NETOPS_TOKEN"].description = "token"
    _build(package, tmp_path)
    for path in (tmp_path / "dist").rglob("*"):
        if path.is_file() and path.suffix in {".json", ".toml", ".md", ".yaml"}:
            assert "supersecret" not in path.read_text(encoding="utf-8", errors="ignore")


def test_copilot_can_embed_a_runtime_bearer_token(package, tmp_path: Path):
    package.target_options["copilot"] = {"_embedded_bearer_token": "pack-time-token"}
    _build(package, tmp_path)
    config = json.loads((tmp_path / "dist" / "build" / "copilot" / "mcp.json").read_text())
    assert config["servers"]["monitoring"]["headers"]["Authorization"] == "Bearer pack-time-token"
    assert "monitoring-authorization" not in {item["id"] for item in config["inputs"]}


def test_imported_http_token_is_embedded_only_for_copilot_and_codex(package, tmp_path: Path):
    token = "Bearer imported-test-token"
    authorization = package.mcp_servers[0].headers["Authorization"]
    authorization.source = EnvVarSource.LITERAL
    authorization.value = token

    _build(package, tmp_path)

    copilot = json.loads((tmp_path / "dist" / "build" / "copilot" / ".mcp.json").read_text())
    assert copilot["mcpServers"]["monitoring"]["headers"]["Authorization"] == token
    assert "monitoring-authorization" not in {
        item["id"] for item in copilot.get("inputs", [])
    }

    codex = json.loads(
        (tmp_path / "dist" / "build" / "codex" / "plugins" / "network-operations" / ".mcp.json")
        .read_text()
    )
    assert codex["mcpServers"]["monitoring"]["headers"]["Authorization"] == token
    assert "bearer_token_env_var" not in codex["mcpServers"]["monitoring"]

    claude = json.loads(
        (tmp_path / "dist" / "build" / "claude-desktop" / "mcpb" / "monitoring" / "manifest.json")
        .read_text()
    )
    assert token not in json.dumps(claude)
    assert "Authorization: Bearer ${user_config.authorization}" in claude["server"]["mcp_config"][
        "args"
    ]

    for target in ("claude-code", "universal"):
        for path in (tmp_path / "dist" / "build" / target).rglob("*"):
            if path.is_file() and path.suffix in {".json", ".yaml", ".md"}:
                assert token not in path.read_text(encoding="utf-8", errors="ignore")


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
    plugin = (
        tmp_path / "dist" / "build" / "claude-desktop" / "cowork-plugin" / "network-operations"
    )
    assert (plugin / ".claude-plugin" / "plugin.json").is_file()
    assert (plugin / "skills" / "network-analysis" / "SKILL.md").is_file()
    assert (plugin / "skills" / "incident-report" / "SKILL.md").is_file()
    # No loose skills tree to copy by hand.
    assert not (tmp_path / "dist" / "build" / "claude-desktop" / "skills").exists()


def test_claude_desktop_bundles_windows_http_bridge(package, tmp_path: Path):
    _build(package, tmp_path)
    manifest = json.loads(
        (
            tmp_path / "dist" / "build" / "claude-desktop" / "mcpb" / "monitoring" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    config = manifest["server"]["mcp_config"]
    assert manifest["server"]["type"] == "binary"
    assert config["command"] == "${__dirname}/server/agentpack-http-bridge-setup.exe"
    assert config["args"][:2] == ["--url", "https://mcp.example.com/mcp"]
    assert "--header" in config["args"]
    assert "Authorization: Bearer ${user_config.authorization}" in config["args"]
    assert manifest["user_config"]["authorization"]["sensitive"] is True
    assert manifest["user_config"]["authorization"]["title"] == "Bearer token"
    manifest_path = (
        tmp_path / "dist" / "build" / "claude-desktop" / "mcpb" / "monitoring"
        / "server" / "agentpack-http-bridge-setup.exe"
    )
    assert manifest_path.is_file()
    assert manifest_path.stat().st_size > 0


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


def test_codex_emits_installable_plugin(package, tmp_path: Path):
    _build(package, tmp_path)
    plugin_dir = tmp_path / "dist" / "build" / "codex" / "plugins" / "network-operations"
    manifest = json.loads(
        (plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "network-operations"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    mcp = json.loads((plugin_dir / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["netops"]["type"] == "stdio"
    marketplace = json.loads(
        (
            tmp_path / "dist" / "build" / "codex" / ".agents" / "plugins" / "marketplace.json"
        ).read_text(encoding="utf-8")
    )
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/network-operations"


def test_codex_uses_an_environment_variable_for_remote_bearer_tokens(package, tmp_path: Path):
    build(package, targets=["codex"], output_dir=tmp_path / "dist")
    mcp = json.loads(
        (tmp_path / "dist" / "build" / "codex" / "plugins" / "network-operations" / ".mcp.json")
        .read_text(encoding="utf-8")
    )
    remote = mcp["mcpServers"]["monitoring"]
    assert remote["bearer_token_env_var"] == "MONITORING_TOKEN"
    assert "headers" not in remote


def test_codex_can_embed_a_runtime_bearer_token(package, tmp_path: Path):
    package.target_options["codex"] = {"_embedded_bearer_token": "pack-time-token"}
    build(package, targets=["codex"], output_dir=tmp_path / "dist")
    mcp = json.loads(
        (tmp_path / "dist" / "build" / "codex" / "plugins" / "network-operations" / ".mcp.json")
        .read_text(encoding="utf-8")
    )
    remote = mcp["mcpServers"]["monitoring"]
    assert remote["headers"]["Authorization"] == "Bearer pack-time-token"
    assert remote["url"] == "https://mcp.example.com/mcp"
    assert remote["type"] == "http"
    assert "bearer_token_env_var" not in remote


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


def test_served_is_the_default_when_the_manifest_says_nothing(package, tmp_path: Path):
    package.build = BuildOptions()
    assert package.build.knowledge is KnowledgeMode.SERVED
    _build(package, tmp_path)
    skill_dir = tmp_path / "dist" / "build" / "universal" / "skills" / "network-analysis"
    assert not (skill_dir / "references").exists()


def test_builds_zipped_skill_as_a_normal_skill_folder(project: Path, tmp_path: Path):
    import zipfile

    archive = project / "skills" / "zipped-skill.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("zipped-skill/SKILL.md", "---\nname: zipped-skill\ndescription: zip\n---\n")
        zf.writestr("zipped-skill/references/reference.md", "source")
    from agentpack.core.diagnostics import Diagnostics
    from agentpack.core.loader import load_package

    package = load_package(project, Diagnostics())
    package.build.knowledge = KnowledgeMode.BUNDLED
    summary = build(package, targets=["universal"], output_dir=tmp_path / "dist")
    assert summary.ok
    skill_dir = tmp_path / "dist" / "build" / "universal" / "skills" / "zipped-skill"
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "references" / "reference.md").read_text(encoding="utf-8") == "source"


def test_strict_mode_fails_on_warnings(package, tmp_path: Path):
    summary = _build(package, tmp_path, strict=True)
    assert summary.diagnostics.warnings
    assert not summary.results


def test_every_archive_names_package_target_and_version(package, tmp_path: Path):
    summary = _build(package, tmp_path, archive=True)
    for result in summary.results:
        assert result.archives, f"{result.target} produced no archive"
        for path in result.archives:
            assert path.name.startswith(f"{result.target}-")
            assert path.stem.endswith("0.1.0")


def test_claude_desktop_archives_are_split_per_server_plus_skills(package, tmp_path: Path):
    summary = _build(package, tmp_path, archive=True)
    claude = next(r for r in summary.results if r.target == "claude-desktop")
    assert sorted(p.name for p in claude.archives) == [
        "claude-desktop-cowork-plugin-0.1.0.plugin",
        "claude-desktop-monitoring-http-mcp.example.com-0.1.0.mcpb",
        "claude-desktop-netops-stdio-0.1.0.mcpb",
    ]


def test_packaging_clears_archives_from_the_previous_run(package, tmp_path: Path):
    output = tmp_path / "dist"
    stale = output / "packages" / "old-package.zip"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    summary = build(package, targets=["universal"], output_dir=output, archive=True)

    assert summary.ok
    assert not stale.exists()
    assert [path.name for path in (output / "packages").iterdir()] == [
        "universal-0.1.0.zip"
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
