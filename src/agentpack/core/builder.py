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
from agentpack.core.fsutil import clean_dir, copy_tree, iter_files, write_json, write_text, zip_dir
from agentpack.core.package_docs import write_guides
from agentpack.core.registry import registry
from agentpack.core.validator import validate
from agentpack.models.package import AgentPackage, BuildResult


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
    if package.build.clean:
        clean_dir(build_root)
        # ``package`` promises a fresh distributable set, not a mixture of the
        # current target selection and archives left by a previous invocation.
        if archive:
            clean_dir(out_root / "packages")
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
        with tempfile.TemporaryDirectory(prefix=f"agentpack-{name}-") as tmp:
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
            # Archives are target-first so an artifact/project name does not leak
            # into a client-facing filename.
            stem = name
            version = package.metadata.version
            if result.archive_specs:
                for spec in result.archive_specs:
                    src = final / spec.root
                    if spec.source_is_file:
                        if not src.is_file():
                            continue
                        destination = packages_dir / (spec.filename or src.name)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, destination)
                        result.archives.append(destination)
                        continue
                    if not src.is_dir():
                        continue
                    result.archives.append(
                        zip_dir(src, packages_dir / f"{stem}-{spec.label}-{version}{spec.suffix}")
                    )
            else:
                result.archives.append(zip_dir(final, packages_dir / f"{stem}-{version}.zip"))
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
        write_guides(out_root / "packages")

    manifest = {
        "agentpackVersion": __version__,
        "package": package.metadata.name,
        "packageVersion": package.metadata.version,
        "knowledgeMode": package.build.knowledge.value,
        "targets": [r.target for r in results],
        "installGuide": guide_path.name,
        "artifacts": artifacts,
        "diagnostics": [d.render() for d in diags],
    }
    manifest_path = out_root / "agentpack-build.json"
    write_json(manifest_path, manifest)

    return BuildSummary(
        results=results,
        diagnostics=diags,
        manifest_path=manifest_path,
        install_guide_path=guide_path,
    )
