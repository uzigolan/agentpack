from __future__ import annotations

from pathlib import Path

import pytest

from agentpack.core.diagnostics import AP1004, AP1007, Diagnostics
from agentpack.core.loader import load_package
from agentpack.core.validator import validate

CHILD_MANIFEST = """apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage
metadata:
  name: {name}
  version: 1.0.0
  description: {name} capabilities.
targets: [universal]
skills:
  - path: skills/
mcp:
  - path: mcp/
"""

SKILL = """---
name: {name}
description: Skill shipped by the {repo} repository.
version: 1.0.0
---

# {name}
"""

MCP = """apiVersion: agentpack.dev/v1alpha1
kind: MCPServer
metadata:
  name: {name}
transport:
  type: stdio
command:
  executable: python
  args: ["-m", "{name}.server"]
"""

AGGREGATOR = """apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage
metadata:
  name: catalog
  version: 2.0.0
  description: Everything.
targets: [universal]
include:
{includes}
"""


def make_repo(root: Path, repo: str, skill: str, server: str) -> Path:
    repo_dir = root / repo
    (repo_dir / "skills" / skill).mkdir(parents=True)
    (repo_dir / "mcp").mkdir(parents=True)
    (repo_dir / "agentpack.yaml").write_text(CHILD_MANIFEST.format(name=repo), encoding="utf-8")
    (repo_dir / "skills" / skill / "SKILL.md").write_text(
        SKILL.format(name=skill, repo=repo), encoding="utf-8"
    )
    (repo_dir / "mcp" / f"{server}.yaml").write_text(MCP.format(name=server), encoding="utf-8")
    return repo_dir


def make_aggregator(root: Path, includes: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "agentpack.yaml").write_text(
        AGGREGATOR.format(includes="\n".join(f"  - path: {p}" for p in includes)),
        encoding="utf-8",
    )
    return root


def test_each_repo_builds_standalone(tmp_path: Path):
    repo = make_repo(tmp_path, "repo-a", "alpha", "alpha-mcp")
    pkg = load_package(repo, Diagnostics())
    assert pkg.metadata.name == "repo-a"
    assert [s.name for s in pkg.skills] == ["alpha"]
    assert [s.name for s in pkg.mcp_servers] == ["alpha-mcp"]


def test_aggregator_composes_child_manifests(tmp_path: Path):
    make_repo(tmp_path / "vendor", "repo-a", "alpha", "alpha-mcp")
    make_repo(tmp_path / "vendor", "repo-b", "beta", "beta-mcp")
    root = make_aggregator(tmp_path / "catalog", ["../vendor/repo-a", "../vendor/repo-b"])

    diags = Diagnostics()
    pkg = load_package(root, diags)

    assert pkg.metadata.name == "catalog"
    assert [s.name for s in pkg.skills] == ["alpha", "beta"]
    assert [s.name for s in pkg.mcp_servers] == ["alpha-mcp", "beta-mcp"]
    assert not diags.has_errors()


def test_include_accepts_a_manifest_file(tmp_path: Path):
    make_repo(tmp_path / "vendor", "repo-a", "alpha", "alpha-mcp")
    root = make_aggregator(tmp_path / "catalog", ["../vendor/repo-a/agentpack.yaml"])
    pkg = load_package(root, Diagnostics())
    assert [s.name for s in pkg.skills] == ["alpha"]


def test_duplicate_names_across_repos_are_errors(tmp_path: Path):
    make_repo(tmp_path / "vendor", "repo-a", "alpha", "shared-mcp")
    make_repo(tmp_path / "vendor", "repo-b", "alpha", "shared-mcp")
    root = make_aggregator(tmp_path / "catalog", ["../vendor/repo-a", "../vendor/repo-b"])

    pkg = load_package(root, Diagnostics())
    diags = validate(pkg, ["universal"])
    codes = {d.code for d in diags.errors}
    assert codes == {AP1004}


def test_missing_include_is_an_error(tmp_path: Path):
    root = make_aggregator(tmp_path / "catalog", ["../vendor/nope"])
    diags = Diagnostics()
    load_package(root, diags)
    assert any(d.code == AP1007 for d in diags.errors)


def test_directory_without_manifest_is_an_error(tmp_path: Path):
    (tmp_path / "vendor" / "plain").mkdir(parents=True)
    root = make_aggregator(tmp_path / "catalog", ["../vendor/plain"])
    diags = Diagnostics()
    load_package(root, diags)
    assert any(d.code == AP1007 for d in diags.errors)


def test_circular_include_is_detected(tmp_path: Path):
    a = make_aggregator(tmp_path / "a", ["../b"])
    make_aggregator(tmp_path / "b", ["../a"])
    diags = Diagnostics()
    load_package(a, diags)
    assert any(d.code == AP1007 and "circular" in d.message for d in diags.errors)


@pytest.mark.parametrize("target", ["universal", "claude-desktop", "copilot"])
def test_aggregated_package_builds(tmp_path: Path, target: str):
    from agentpack.core.builder import build

    make_repo(tmp_path / "vendor", "repo-a", "alpha", "alpha-mcp")
    make_repo(tmp_path / "vendor", "repo-b", "beta", "beta-mcp")
    root = make_aggregator(tmp_path / "catalog", ["../vendor/repo-a", "../vendor/repo-b"])

    pkg = load_package(root, Diagnostics())
    summary = build(pkg, targets=[target], output_dir=tmp_path / "dist")
    assert summary.ok
    assert summary.results[0].files
