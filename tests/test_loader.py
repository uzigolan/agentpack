from __future__ import annotations

from pathlib import Path

import pytest

from agentpack.core.diagnostics import AP1004, AP1005, AP1006, AgentPackError, Diagnostics
from agentpack.core.fsutil import ensure_inside
from agentpack.core.loader import load_package, load_skill, parse_frontmatter
from agentpack.core.validator import validate
from agentpack.models.package import TransportType


def test_loads_skills_and_servers(package):
    assert [s.name for s in package.skills] == ["incident-report", "network-analysis"]
    assert [s.name for s in package.mcp_servers] == ["monitoring", "netops"]
    assert package.mcp_servers[0].transport is TransportType.HTTP
    assert package.mcp_servers[1].transport is TransportType.STDIO


def test_skill_references_detected(package):
    analysis = next(s for s in package.skills if s.name == "network-analysis")
    assert analysis.has_references
    assert analysis.version == "1.0.0"


def test_secrets_are_never_valued(package):
    token = package.mcp_servers[1].environment["NETOPS_TOKEN"]
    assert token.secret and token.value is None
    literal = package.mcp_servers[1].environment["NETOPS_READONLY"]
    assert literal.value == "true" and not literal.secret


def test_user_inputs_include_headers(package):
    monitoring = package.mcp_servers[0]
    assert "Authorization" in monitoring.user_inputs()


def test_frontmatter_name_must_match_directory(tmp_path: Path):
    skill_dir = tmp_path / "mismatch"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: other\ndescription: x\n---\n\nbody\n", encoding="utf-8"
    )
    diags = Diagnostics()
    load_skill(skill_dir, diags)
    assert any(d.code == AP1005 for d in diags.errors)


def test_missing_description_is_an_error(tmp_path: Path):
    skill_dir = tmp_path / "nodesc"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: nodesc\n---\n\nbody\n", encoding="utf-8")
    diags = Diagnostics()
    load_skill(skill_dir, diags)
    assert any(d.code == AP1005 for d in diags.errors)


def test_duplicate_skill_names_are_reported(project: Path):
    duplicate = project / "skills2" / "incident-report"
    duplicate.mkdir(parents=True)
    (duplicate / "SKILL.md").write_text(
        "---\nname: incident-report\ndescription: dupe\n---\n", encoding="utf-8"
    )
    manifest = project / "agentpack.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "  - path: skills/", "  - path: skills/\n  - path: skills2/"
        ),
        encoding="utf-8",
    )
    pkg = load_package(project, Diagnostics())
    diags = validate(pkg, ["universal"])
    assert any(d.code == AP1004 for d in diags.errors)


def test_unknown_target_is_an_error(package):
    diags = validate(package, ["not-a-client"])
    assert any(d.code == "AP2001" for d in diags.errors)


def test_path_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(AgentPackError) as exc:
        ensure_inside(tmp_path, tmp_path / ".." / "escape")
    assert exc.value.code == AP1006


def test_parse_frontmatter_without_frontmatter():
    meta, body = parse_frontmatter("# no frontmatter\n")
    assert meta == {} and body.startswith("# no")
