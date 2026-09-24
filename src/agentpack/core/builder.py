"""Build pipeline: staging directory -> validation -> dist/ -> build manifest."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agentpack import __version__
from agentpack.adapters.base import TargetAdapter
from agentpack.core import install_guide
from agentpack.core.diagnostics import AP2001, AP3001, Diagnostics
from agentpack.core.fsutil import (
    clean_dir,
    copy_tree,
    iter_files,
    remove_tree,
    write_json,
    write_text,
    zip_dir,
)
from agentpack.core.package_docs import write_guides
from agentpack.core.registry import registry
from agentpack.core.validator import validate
from agentpack.models.package import AgentPackage, BuildResult, MCPServer, TransportType


@dataclass
class BuildSummary:
    results: list[BuildResult]
    diagnostics: Diagnostics
    manifest_path: Path | None = None
    install_guide_path: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics.has_errors()


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    for rel in iter_files(path):
        h.update(str(rel).replace("\\", "/").encode())
        h.update((path / rel).read_bytes())
    return h.hexdigest()


def _safe_segment(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in ".-" else "-" for char in value.lower())
    return safe.strip(".-") or "package"


def _server_transport_label(server: MCPServer) -> str:
    if not server.is_remote:
        return TransportType.STDIO.value
    if not server.endpoint:
        return server.transport.value
    hostname = server.endpoint.url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    safe_hostname = _safe_segment(hostname)
    return f"{server.transport.value}-{safe_hostname or 'remote'}"


def _package_transport_label(package: AgentPackage) -> str:
    labels = sorted({_server_transport_label(server) for server in package.mcp_servers})
    if not labels:
        return "no-mcp"
    if len(labels) == 1:
        return labels[0]
    return "mixed"


def _archive_filename(
    package: AgentPackage,
    target: str,
    *,
    label: str | None = None,
    suffix: str = ".zip",
) -> str:
    parts = [_safe_segment(target)]
    if label:
        parts.append(_safe_segment(label))
    if suffix != ".mcpb":
        parts.append(_package_transport_label(package))
    parts.append(_safe_segment(package.metadata.version))
    return "-".join(parts) + suffix


def build(
    package: AgentPackage,
    *,
    targets: list[str] | None = None,
    output_dir: Path | None = None,
    strict: bool = False,
    archive: bool = False,
) -> BuildSummary:
    selected = targets or package.targets
    diags = validate(package, selected)

    if diags.has_errors() or (strict and diags.warnings):
        return BuildSummary(results=[], diagnostics=diags)

    out_root = output_dir or (package.project_dir / package.build.output)
    build_root = out_root / "build"
    packages_dir = out_root / "packages"
    is_partial_build = targets is not None
    if package.build.clean:
        if not is_partial_build:
            clean_dir(build_root)
            # ``package`` promises a fresh distributable set, not a mixture of the
            # current target selection and archives left by a previous invocation.
            if archive:
                clean_dir(packages_dir)
        else:
            for name in selected:
                clean_dir(build_root / name)
    build_root.mkdir(parents=True, exist_ok=True)

    results: list[BuildResult] = []
    artifacts: list[dict[str, object]] = []
    built: list[tuple[TargetAdapter, BuildResult]] = []

    for name in selected:
        adapter = registry.get(name)
        if adapter is None:
            diags.error(AP2001, f"unknown target '{name}'", target=name)
            continue

        # Build into a temp dir so a failed target leaves no misleading output.
        tmp = Path(tempfile.mkdtemp(prefix=f"agentpack-{name}-"))
        try:
            staging = Path(tmp) / name
            staging.mkdir(parents=True)
            try:
                result = adapter.build(package, staging)
            except Exception as exc:  # noqa: BLE001 - surfaced as a diagnostic
                diags.error(AP3001, f"{type(exc).__name__}: {exc}", target=name)
                continue

            final = build_root / name
            clean_dir(final)
            copy_tree(staging, final)
        finally:
            remove_tree(tmp)

        result.output_dir = final
        result.files = [str(p).replace("\\", "/") for p in iter_files(final)]
        entry: dict[str, object] = {
            "target": name,
            "adapterVersion": adapter.adapter_version,
            "type": result.artifact_type.value,
            "path": str(final.relative_to(out_root)).replace("\\", "/"),
            "fileCount": len(result.files),
            "sha256": _digest(final),
        }

        if archive:
            packages_dir = out_root / "packages"
            stem = name
            if is_partial_build and packages_dir.is_dir():
                known_targets = set(registry.names())
                stem_prefix = f"{_safe_segment(stem)}-"
                stem_dot = f"{_safe_segment(stem)}."
                for existing in list(packages_dir.iterdir()):
                    if not existing.is_file():
                        continue
                    if existing.name.startswith(stem_prefix) or existing.name.startswith(stem_dot):
                        existing.unlink()
                        continue
                    if existing.name.startswith("INSTALL"):
                        continue
                    matches_other_target = any(
                        existing.name.startswith(f"{_safe_segment(t)}-")
                        or existing.name.startswith(f"{_safe_segment(t)}.")
                        for t in known_targets
                        if t != name
                    )
                    if not matches_other_target:
                        existing.unlink()
            if result.archive_specs:
                for spec in result.archive_specs:
                    src = final / spec.root
                    if spec.source_is_file:
                        if not src.is_file():
                            continue
                        filename = spec.filename or _archive_filename(
                            package, stem, label=spec.label, suffix=src.suffix
                        )
                        destination = packages_dir / filename
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, destination)
                        result.archives.append(destination)
                        continue
                    if not src.is_dir():
                        continue
                    result.archives.append(
                        zip_dir(
                            src,
                            packages_dir
                            / _archive_filename(package, stem, label=spec.label, suffix=spec.suffix),
                            arc_root=spec.arc_root,
                        )
                    )
            else:
                result.archives.append(
                    zip_dir(final, packages_dir / _archive_filename(package, stem))
                )
            entry["archives"] = [
                str(a.relative_to(out_root)).replace("\\", "/") for a in result.archives
            ]

        artifacts.append(entry)
        results.append(result)
        built.append((adapter, result))

    guide_path = out_root / "INSTALL.md"
    write_text(guide_path, install_guide.render(package, built, out_root))
    if archive and results:
        # These recipient-facing guides inspect only the finished package files.
        # They intentionally do not inherit manifest/build options.
        write_guides(
            out_root / "packages",
            name_suffix=f"{_package_transport_label(package)}-{_safe_segment(package.metadata.version)}",
        )

    manifest_path = out_root / "agentpack-build.json"
    target_names = [r.target for r in results]
    if is_partial_build and manifest_path.is_file():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            preserved_targets = [t for t in old_manifest.get("targets", []) if t not in target_names]
            preserved_artifacts = [
                a for a in old_manifest.get("artifacts", []) if a.get("target") not in target_names
            ]
            target_names = preserved_targets + target_names
            artifacts = preserved_artifacts + artifacts
        except Exception:
            pass

    manifest = {
        "agentpackVersion": __version__,
        "package": package.metadata.name,
        "packageVersion": package.metadata.version,
        "knowledgeMode": package.build.knowledge.value,
        "targets": target_names,
        "installGuide": guide_path.name,
        "artifacts": artifacts,
        "diagnostics": [d.render() for d in diags],
    }
    write_json(manifest_path, manifest)

    return BuildSummary(
        results=results,
        diagnostics=diags,
        manifest_path=manifest_path,
        install_guide_path=guide_path,
    )
