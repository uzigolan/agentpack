from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from agentpack.cli import app

runner = CliRunner()


def init(tmp_path: Path, *extra: str) -> Path:
    root = tmp_path / "proj"
    result = runner.invoke(app, ["init", str(root), "--name", "demo", *extra])
    assert result.exit_code == 0, result.output
    return root / "agentpack.yaml"


def read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_skill(root: Path, name: str) -> None:
    directory = root / "skills" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill.\nversion: 1.0.0\n---\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------
def test_init_takes_a_name_and_manifest_filename(tmp_path: Path):
    root = tmp_path / "anything"
    result = runner.invoke(
        app, ["init", str(root), "--name", "netops-skills", "-f", "netops.agentpack.yaml"]
    )
    assert result.exit_code == 0, result.output
    manifest = root / "netops.agentpack.yaml"
    assert manifest.is_file()
    assert read(manifest)["metadata"]["name"] == "netops-skills"
    assert "-f netops.agentpack.yaml" in result.output


def test_init_accepts_a_package_version(tmp_path: Path):
    root = tmp_path / "anything"
    result = runner.invoke(app, ["init", str(root), "-n", "netops-skills", "--version", "1.4.0"])
    assert result.exit_code == 0, result.output
    assert read(root / "agentpack.yaml")["metadata"]["version"] == "1.4.0"


def test_init_writes_only_the_manifest_by_default(tmp_path: Path):
    manifest = init(tmp_path)
    assert not (manifest.parent / "skills").exists()
    assert not (manifest.parent / "mcp").exists()
    data = read(manifest)
    assert data["skills"] == [] and data["mcp"] == []
    assert sorted(p.name for p in manifest.parent.iterdir()) == [
        ".gitignore",
        "README.md",
        "agentpack.yaml",
    ]


def test_init_example_scaffolds_skills_and_mcp(tmp_path: Path):
    manifest = init(tmp_path, "--example")
    assert (manifest.parent / "skills" / "example" / "SKILL.md").is_file()
    assert (manifest.parent / "mcp" / "example.yaml").is_file()
    assert read(manifest)["skills"] == [{"path": "skills/"}]


def test_init_output_sets_the_artifact_folder(tmp_path: Path):
    manifest = init(tmp_path, "-o", "artifacts")
    assert read(manifest)["build"]["output"] == "artifacts"
    assert "artifacts/" in (manifest.parent / ".gitignore").read_text(encoding="utf-8")

    result = runner.invoke(app, ["package", "-f", str(manifest), "-t", "universal"])
    assert result.exit_code == 0, result.output
    assert (manifest.parent / "artifacts" / "INSTALL.md").is_file()
    assert (manifest.parent / "artifacts" / "packages").is_dir()
    assert not (manifest.parent / "dist").exists()


def test_init_defaults_the_name_to_the_directory(tmp_path: Path):
    root = tmp_path / "my-package"
    runner.invoke(app, ["init", str(root)])
    assert read(root / "agentpack.yaml")["metadata"]["name"] == "my-package"


def test_init_without_a_directory_creates_an_artifacts_package(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--name", "rad-agent-toolkit"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "artifacts" / "rad-agent-toolkit" / "agentpack.yaml").is_file()


# --------------------------------------------------------------------------
# skill add / remove
# --------------------------------------------------------------------------
def test_skill_add_is_idempotent(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")

    first = runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])
    second = runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])

    assert first.exit_code == 0 and second.exit_code == 0
    assert "Already registered" in second.output
    assert read(manifest)["skills"] == [{"path": "skills/alpha"}]


def test_skill_add_recognises_a_covering_directory(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")
    runner.invoke(app, ["skill", "add", "skills", "-f", str(manifest)])

    result = runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])
    assert "Already registered via 'skills: skills'" in result.output
    assert read(manifest)["skills"] == [{"path": "skills"}]


def test_skill_add_warns_when_the_directory_is_missing(tmp_path: Path):
    manifest = init(tmp_path)
    result = runner.invoke(app, ["skill", "add", "skills/ghost", "-f", str(manifest)])
    assert result.exit_code == 0
    assert "no SKILL.md found" in result.output


def test_skill_add_reports_the_skills_it_found(tmp_path: Path):
    manifest = init(tmp_path)
    for name in ("alpha", "beta"):
        make_skill(manifest.parent, name)

    result = runner.invoke(app, ["skill", "add", "skills", "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "2 skill(s): alpha, beta" in result.output


def test_skill_add_accepts_an_absolute_path_inside_the_project(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")

    absolute = manifest.parent / "skills" / "alpha"
    result = runner.invoke(app, ["skill", "add", str(absolute), "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert read(manifest)["skills"] == [{"path": "skills/alpha"}]


def test_skill_add_rejects_a_path_outside_the_project(tmp_path: Path):
    manifest = init(tmp_path)
    outside = tmp_path / "elsewhere" / "skills"
    outside.mkdir(parents=True)

    result = runner.invoke(app, ["skill", "add", str(outside), "-f", str(manifest)])
    assert result.exit_code == 1
    assert "is outside the project" in result.output
    assert read(manifest)["skills"] == []


def test_skill_import_copies_an_external_collection_into_the_package(tmp_path: Path):
    manifest = init(tmp_path)
    external = tmp_path / "source-repo" / "skills"
    for name in ("alpha", "beta"):
        directory = external / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill.\n---\n", encoding="utf-8"
        )
    (external / "alpha" / "references").mkdir()
    (external / "alpha" / "references" / "guide.md").write_text("guide", encoding="utf-8")

    result = runner.invoke(app, ["skill", "import", str(external), "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert (manifest.parent / "skills" / "alpha" / "references" / "guide.md").is_file()
    assert (manifest.parent / "skills" / "beta" / "SKILL.md").is_file()
    assert read(manifest)["skills"] == [{"path": "skills"}]


def test_skill_import_confirms_before_overwriting(tmp_path: Path):
    manifest = init(tmp_path)
    external = tmp_path / "source" / "skills" / "alpha"
    external.mkdir(parents=True)
    (external / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: new text\n---\n", encoding="utf-8"
    )
    target = manifest.parent / "skills" / "alpha"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: old text\n---\n", encoding="utf-8"
    )

    result = runner.invoke(
        app, ["skill", "import", str(external.parent), "-f", str(manifest)], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "new text" in (target / "SKILL.md").read_text(encoding="utf-8")


def test_name_selects_the_artifacts_workspace_for_everyday_commands(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init", "-n", "demo"])
    external = tmp_path / "source" / "skills" / "alpha"
    external.mkdir(parents=True)
    (external / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: alpha skill.\n---\n", encoding="utf-8"
    )

    imported = runner.invoke(app, ["skill", "import", str(external.parent), "-n", "demo"])
    built = runner.invoke(app, ["package", "-n", "demo", "-t", "universal"])

    assert imported.exit_code == 0, imported.output
    assert built.exit_code == 0, built.output
    assert (tmp_path / "artifacts" / "demo" / "skills" / "alpha" / "SKILL.md").is_file()
    package = tmp_path / "artifacts" / "demo" / "dist" / "packages" / "universal-0.1.0.zip"
    assert package.is_file()


def test_version_set_updates_the_named_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init", "-n", "demo"])
    result = runner.invoke(app, ["version", "set", "2.1.0", "-n", "demo"])
    assert result.exit_code == 0, result.output
    manifest = tmp_path / "artifacts" / "demo" / "agentpack.yaml"
    assert read(manifest)["metadata"]["version"] == "2.1.0"


def test_skill_remove(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")
    runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])

    result = runner.invoke(app, ["skill", "remove", "skills/alpha", "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert read(manifest)["skills"] == []
    assert (manifest.parent / "skills" / "alpha" / "SKILL.md").is_file()


# --------------------------------------------------------------------------
# mcp add / update / remove
# --------------------------------------------------------------------------
def test_mcp_add_stdio(tmp_path: Path):
    manifest = init(tmp_path)
    result = runner.invoke(
        app,
        # fmt: off
        [
            "mcp", "add", "netops", "-f", str(manifest),
            "--command", "python", "--arg", "-m", "--arg", "netops_mcp.server",
            "--secret", "NETOPS_TOKEN", "--env", "NETOPS_READONLY=true",
        ],
        # fmt: on
    )
    assert result.exit_code == 0, result.output

    server = read(manifest.parent / "mcp" / "netops.yaml")
    assert server["transport"]["type"] == "stdio"
    assert server["command"]["args"] == ["-m", "netops_mcp.server"]
    assert server["environment"]["NETOPS_TOKEN"] == {
        "source": "user",
        "required": True,
        "secret": True,
        "description": "Secret value for NETOPS_TOKEN.",
    }
    assert server["environment"]["NETOPS_READONLY"] == {"source": "literal", "value": "true"}
    assert read(manifest)["mcp"] == [{"path": "mcp"}]


def test_mcp_add_http_registers_the_directory_once(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "a", "-f", str(manifest), "-c", "python"])
    runner.invoke(
        app,
        ["mcp", "add", "b", "-f", str(manifest), "-t", "http", "-u", "https://x/mcp",
         "--header", "Authorization"],
    )
    assert read(manifest)["mcp"] == [{"path": "mcp"}]
    server = read(manifest.parent / "mcp" / "b.yaml")
    assert server["endpoint"]["url"] == "https://x/mcp"
    assert server["headers"]["Authorization"]["secret"] is True


def test_mcp_add_refuses_to_overwrite(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])
    result = runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "node"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_mcp_add_stdio_without_command_fails(tmp_path: Path):
    manifest = init(tmp_path)
    result = runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest)])
    assert result.exit_code == 1
    assert "needs --command" in result.output


def test_mcp_update_touches_only_given_fields(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(
        app,
        ["mcp", "add", "netops", "-f", str(manifest), "-c", "python", "-a", "-m",
         "--secret", "NETOPS_TOKEN"],
    )

    result = runner.invoke(
        app, ["mcp", "update", "netops", "-f", str(manifest), "-d", "Read only", "-e", "X=1"]
    )
    assert result.exit_code == 0, result.output

    server = read(manifest.parent / "mcp" / "netops.yaml")
    assert server["metadata"]["description"] == "Read only"
    assert server["environment"]["X"] == {"source": "literal", "value": "1"}
    assert server["environment"]["NETOPS_TOKEN"]["secret"] is True
    assert server["command"]["executable"] == "python"


def test_mcp_update_can_drop_an_env_key(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python", "-e", "X=1"])
    runner.invoke(app, ["mcp", "update", "netops", "-f", str(manifest), "--remove-env", "X"])
    assert read(manifest.parent / "mcp" / "netops.yaml")["environment"] == {}


def test_mcp_update_without_options_changes_nothing(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])
    before = (manifest.parent / "mcp" / "netops.yaml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["mcp", "update", "netops", "-f", str(manifest)])
    assert "nothing changed" in result.output
    assert (manifest.parent / "mcp" / "netops.yaml").read_text(encoding="utf-8") == before


def test_mcp_remove_deletes_the_file(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])

    result = runner.invoke(app, ["mcp", "remove", "netops", "-f", str(manifest)])
    assert result.exit_code == 0, result.output
    assert not (manifest.parent / "mcp" / "netops.yaml").exists()


def test_mcp_remove_unknown_name_fails(tmp_path: Path):
    manifest = init(tmp_path)
    result = runner.invoke(app, ["mcp", "remove", "ghost", "-f", str(manifest)])
    assert result.exit_code == 1
    assert "No MCP definition named 'ghost'" in result.output


def test_manifest_comments_survive_editing(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")
    runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])

    text = manifest.read_text(encoding="utf-8")
    assert "# Register capabilities with:" in text
    assert "# served | bundled" in text


def test_edited_project_builds(tmp_path: Path):
    manifest = init(tmp_path)
    make_skill(manifest.parent, "alpha")
    runner.invoke(app, ["skill", "add", "skills/alpha", "-f", str(manifest)])
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])

    result = runner.invoke(app, ["package", "-f", str(manifest), "-t", "universal"])
    assert result.exit_code == 0, result.output
    assert (manifest.parent / "dist" / "packages" / "universal-0.1.0.zip").is_file()


# --------------------------------------------------------------------------
# mcp import
# --------------------------------------------------------------------------
def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_import_claude_style_json(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "claude.json",
        {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@example/github-mcp"],
                    "env": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
                },
                "monitoring": {"type": "http", "url": "https://mcp.example.com/mcp"},
            }
        },
    )

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert result.exit_code == 0, result.output

    github = read(manifest.parent / "mcp" / "github.yaml")
    assert github["command"] == {"executable": "npx", "args": ["-y", "@example/github-mcp"]}
    # A real credential in the source is never carried over.
    assert github["environment"]["GITHUB_TOKEN"] == {
        "source": "user",
        "required": True,
        "secret": True,
        "description": "Value for GITHUB_TOKEN.",
    }
    assert "ghp_realsecretvalue" not in (manifest.parent / "mcp" / "github.yaml").read_text(
        encoding="utf-8"
    )
    assert read(manifest.parent / "mcp" / "monitoring.yaml")["transport"]["type"] == "http"
    assert read(manifest)["mcp"] == [{"path": "mcp"}]


def test_import_vscode_style_json_uses_input_metadata(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "mcp.json",
        {
            "inputs": [
                {
                    "type": "promptString",
                    "id": "netops-token",
                    "description": "Gateway token",
                    "password": True,
                },
                {"type": "promptString", "id": "netops-inventory", "password": False},
            ],
            "servers": {
                "netops": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "netops_mcp.server"],
                    "env": {
                        "NETOPS_TOKEN": "${input:netops-token}",
                        "NETOPS_INVENTORY": "${input:netops-inventory}",
                        "NETOPS_READONLY": "true",
                    },
                }
            },
        },
    )

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert result.exit_code == 0, result.output

    env = read(manifest.parent / "mcp" / "netops.yaml")["environment"]
    assert env["NETOPS_TOKEN"]["secret"] is True
    assert env["NETOPS_TOKEN"]["description"] == "Gateway token"
    assert env["NETOPS_INVENTORY"] == {
        "source": "user",
        "required": True,
        "secret": False,
        "description": "Value for NETOPS_INVENTORY.",
    }
    assert env["NETOPS_READONLY"] == {"source": "literal", "value": "true"}


def test_import_preserves_a_real_secret_http_header_for_plugin_targets(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "remote.json",
        {
            "mcpServers": {
                "monitoring": {
                    "type": "http",
                    "url": "https://mcp.example.com/mcp",
                    "headers": {"Authorization": "Bearer imported-test-token"},
                }
            }
        },
    )

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert result.exit_code == 0, result.output

    authorization = read(manifest.parent / "mcp" / "monitoring.yaml")["headers"]["Authorization"]
    assert authorization == {
        "source": "literal",
        "value": "Bearer imported-test-token",
        "required": True,
        "secret": True,
        "description": "Value for Authorization.",
    }


def test_import_mcpb_manifest(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "manifest.json",
        {
            "manifest_version": "0.3",
            "name": "netops",
            "description": "From a bundle",
            "server": {
                "type": "python",
                "entry_point": "netops_mcp.server",
                "mcp_config": {
                    "command": "python",
                    "args": ["-m", "netops_mcp.server"],
                    "env": {"NETOPS_TOKEN": "${user_config.netops_token}"},
                },
            },
            "user_config": {
                "netops_token": {"type": "string", "sensitive": True, "description": "Token"}
            },
        },
    )

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert result.exit_code == 0, result.output

    server = read(manifest.parent / "mcp" / "netops.yaml")
    assert server["command"]["executable"] == "python"
    assert server["environment"]["NETOPS_TOKEN"]["secret"] is True
    assert server["environment"]["NETOPS_TOKEN"]["description"] == "Token"


def test_import_bare_object_needs_a_name(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(tmp_path / "one.json", {"command": "npx", "args": ["-y", "thing"]})

    without = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert without.exit_code == 1
    assert "needs --name" in without.output

    with_name = runner.invoke(
        app, ["mcp", "import", str(source), "-f", str(manifest), "--server", "thing"]
    )
    assert with_name.exit_code == 0, with_name.output
    assert (manifest.parent / "mcp" / "thing.yaml").is_file()


def test_import_can_select_one_server(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "many.json",
        {"mcpServers": {"a": {"command": "a"}, "b": {"command": "b"}}},
    )
    runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest), "-s", "b"])
    assert (manifest.parent / "mcp" / "b.yaml").is_file()
    assert not (manifest.parent / "mcp" / "a.yaml").exists()


def test_import_does_not_overwrite_without_update(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])
    source = write_json(tmp_path / "j.json", {"mcpServers": {"netops": {"command": "node"}}})

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)], input="n\n")
    assert "exists" in result.output
    assert read(manifest.parent / "mcp" / "netops.yaml")["command"]["executable"] == "python"


def test_import_overwrites_mcp_definition_after_confirmation(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])
    source = write_json(tmp_path / "j.json", {"mcpServers": {"netops": {"command": "node"}}})

    result = runner.invoke(
        app, ["mcp", "import", str(source), "-f", str(manifest)], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert read(manifest.parent / "mcp" / "netops.yaml")["command"]["executable"] == "node"


def test_import_update_merges_values(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(
        app,
        ["mcp", "add", "netops", "-f", str(manifest), "-c", "python", "--secret", "NETOPS_TOKEN"],
    )
    source = write_json(
        tmp_path / "j.json",
        {"mcpServers": {"netops": {"command": "node", "args": ["server.js"], "env": {"X": "1"}}}},
    )

    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest), "--update"])
    assert result.exit_code == 0, result.output

    server = read(manifest.parent / "mcp" / "netops.yaml")
    assert server["command"] == {"executable": "node", "args": ["server.js"]}
    assert server["environment"]["X"] == {"source": "literal", "value": "1"}
    assert server["environment"]["NETOPS_TOKEN"]["secret"] is True


def test_import_update_switching_to_http_drops_the_command(tmp_path: Path):
    manifest = init(tmp_path)
    runner.invoke(app, ["mcp", "add", "netops", "-f", str(manifest), "-c", "python"])
    source = write_json(
        tmp_path / "j.json",
        {"mcpServers": {"netops": {"type": "http", "url": "https://x/mcp"}}},
    )
    runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest), "-u"])

    server = read(manifest.parent / "mcp" / "netops.yaml")
    assert server["transport"]["type"] == "http"
    assert "command" not in server
    assert server["endpoint"]["url"] == "https://x/mcp"


def test_import_rejects_unrecognised_json(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(tmp_path / "j.json", {"unrelated": True})
    result = runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])
    assert result.exit_code == 1
    assert "no MCP server found" in result.output


def test_imported_project_builds(tmp_path: Path):
    manifest = init(tmp_path)
    source = write_json(
        tmp_path / "j.json",
        {"mcpServers": {"netops": {"command": "python", "args": ["-m", "s"]}}},
    )
    runner.invoke(app, ["mcp", "import", str(source), "-f", str(manifest)])

    result = runner.invoke(app, ["build", "-f", str(manifest), "-t", "copilot"])
    assert result.exit_code == 0, result.output
