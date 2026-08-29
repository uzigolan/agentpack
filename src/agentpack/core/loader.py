"""Load a canonical project directory into the normalized model."""

from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path
from typing import Any

import yaml

from agentpack import API_VERSION
from agentpack.core.diagnostics import (
    AP1001,
    AP1002,
    AP1003,
    AP1005,
    AP1006,
    AP1007,
    AP2001,
    AgentPackError,
    Diagnostics,
)
from agentpack.core.fsutil import ensure_inside, iter_files
from agentpack.models.package import (
    AgentPackage,
    BuildOptions,
    Command,
    Endpoint,
    EnvVar,
    FileAsset,
    MCPCapabilities,
    MCPServer,
    PackageMetadata,
    Skill,
    TransportType,
    UnsupportedFeaturePolicy,
)

MANIFEST_NAMES = ("agentpack.yaml", "agentpack.yml")
SKILL_FILE = "SKILL.md"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)

_ASSET_KINDS = {
    "prompts": "prompt",
    "instructions": "instruction",
    "agents": "agent",
    "commands": "command",
    "hooks": "hook",
    "assets": "asset",
}

# The first AgentPack builds exported IDE-specific Copilot workspace trees.
# Copilot is now packaged as one UI-installable, host-neutral plugin.
_TARGET_ALIASES = {
    "copilot-vscode": "copilot",
    "copilot-intellij": "copilot",
}


def find_project(start: Path) -> Path:
    """Walk upwards looking for a manifest."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if any((candidate / n).is_file() for n in MANIFEST_NAMES):
            return candidate
    raise AgentPackError(AP1001, f"no agentpack.yaml found at or above {start}")


def manifest_path(project_dir: Path) -> Path:
    for name in MANIFEST_NAMES:
        p = project_dir / name
        if p.is_file():
            return p
    raise AgentPackError(AP1001, f"no agentpack.yaml in {project_dir}")


def resolve_manifest(source: Path) -> Path:
    """Accept a manifest file (any name) or a directory searched upwards."""
    source = source.resolve()
    if source.is_file():
        return source
    if not source.exists():
        raise AgentPackError(AP1001, f"path not found: {source}")
    return manifest_path(find_project(source))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AgentPackError(AP1001, f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentPackError(AP1001, f"{path.name} must contain a YAML mapping")
    return data


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise AgentPackError(AP1005, "SKILL.md frontmatter must be a YAML mapping")
    return meta, match.group(2)


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------
def load_skill(skill_dir: Path, diags: Diagnostics) -> Skill | None:
    md = skill_dir / SKILL_FILE
    if not md.is_file():
        diags.error(AP1002, f"missing {SKILL_FILE}", source=str(skill_dir))
        return None

    text = md.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    name = str(meta.get("name") or skill_dir.name)
    if name != skill_dir.name:
        # Enforced because every client resolves skills by directory name.
        diags.error(
            AP1005,
            f"frontmatter name '{name}' must match directory name '{skill_dir.name}'",
            source=str(md),
        )
    description = str(meta.get("description") or "").strip()
    if not description:
        diags.error(AP1005, "frontmatter 'description' is required", source=str(md))

    version = meta.get("version")
    if version is not None and not re.fullmatch(r"\d+\.\d+\.\d+", str(version)):
        diags.warning(AP1005, f"version '{version}' is not MAJOR.MINOR.PATCH", source=str(md))

    files = [p for p in iter_files(skill_dir) if p.name != SKILL_FILE]
    return Skill(
        name=skill_dir.name,
        description=description,
        version=str(version) if version is not None else None,
        source_dir=skill_dir,
        skill_md=md,
        frontmatter=meta,
        body=body,
        files=files,
    )


def _zip_member_is_safe(member: zipfile.ZipInfo) -> bool:
    """Reject paths and links that could escape a generated artifact."""
    path = member.filename.replace("\\", "/")
    parts = tuple(part for part in path.split("/") if part)
    if not path or path.startswith("/") or (parts and ":" in parts[0]):
        return False
    if any(part == ".." for part in parts):
        return False
    return not stat.S_ISLNK(member.external_attr >> 16)


def _load_zip_skill(archive: Path, skill_md_member: str, diags: Diagnostics) -> Skill | None:
    """Load one skill root from a ZIP without extracting untrusted input."""
    root = skill_md_member.rsplit("/", 1)[0] if "/" in skill_md_member else ""
    name = Path(root).name if root else archive.stem
    try:
        with zipfile.ZipFile(archive) as zf:
            text = zf.read(skill_md_member).decode("utf-8")
            members = sorted(
                member.filename
                for member in zf.infolist()
                if not member.is_dir()
                and member.filename.startswith(f"{root}/" if root else "")
                and member.filename != skill_md_member
            )
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        diags.error(AP1002, f"invalid skill ZIP: {exc}", source=str(archive))
        return None

    meta, body = parse_frontmatter(text)
    declared_name = str(meta.get("name") or name)
    if declared_name != name:
        diags.error(
            AP1005,
            f"frontmatter name '{declared_name}' must match skill root '{name}'",
            source=f"{archive}!/{skill_md_member}",
        )
    description = str(meta.get("description") or "").strip()
    if not description:
        diags.error(
            AP1005, "frontmatter 'description' is required", source=f"{archive}!/{skill_md_member}"
        )
    version = meta.get("version")
    if version is not None and not re.fullmatch(r"\d+\.\d+\.\d+", str(version)):
        diags.warning(
            AP1005,
            f"version '{version}' is not MAJOR.MINOR.PATCH",
            source=f"{archive}!/{skill_md_member}",
        )
    prefix = f"{root}/" if root else ""
    return Skill(
        name=name,
        description=description,
        version=str(version) if version is not None else None,
        source_dir=archive,
        skill_md=archive,
        frontmatter=meta,
        body=body,
        files=[Path(member.removeprefix(prefix)) for member in members],
        source_archive=archive,
        archive_root=root,
    )


def load_skill_zip(archive: Path, diags: Diagnostics) -> list[Skill]:
    """Load every skill root in a ZIP (one skill or a whole skills collection)."""
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            unsafe = next((member for member in members if not _zip_member_is_safe(member)), None)
            if unsafe:
                diags.error(
                    AP1006,
                    f"unsafe path or symlink in skill ZIP: {unsafe.filename}",
                    source=str(archive),
                )
                return []
            skill_mds = sorted(
                member.filename
                for member in members
                if not member.is_dir() and Path(member.filename).name == SKILL_FILE
            )
    except (OSError, zipfile.BadZipFile) as exc:
        diags.error(AP1002, f"invalid skill ZIP: {exc}", source=str(archive))
        return []
    if not skill_mds:
        diags.error(AP1002, "ZIP contains no SKILL.md", source=str(archive))
        return []
    return [skill for member in skill_mds if (skill := _load_zip_skill(archive, member, diags))]


def _skill_candidates(path: Path) -> tuple[list[Path], list[Path]]:
    """Discover all directory and ZIP skills below a registered skill path."""
    if path.is_file():
        directories = [path.parent] if path.name == SKILL_FILE else []
        archives = [path] if path.suffix.lower() == ".zip" else []
        return directories, archives
    if not path.is_dir():
        return [], []
    if (path / SKILL_FILE).is_file():
        return [path], []
    directories = sorted({skill_md.parent for skill_md in path.rglob(SKILL_FILE)})
    archives = sorted(path.rglob("*.zip"))
    return directories, archives


# --------------------------------------------------------------------------
# MCP servers
# --------------------------------------------------------------------------
def _env_map(raw: Any, where: str) -> dict[str, EnvVar]:
    out: dict[str, EnvVar] = {}
    for key, value in (raw or {}).items():
        if isinstance(value, str):
            out[key] = EnvVar(source="literal", value=value, secret=False, required=True)
        elif isinstance(value, dict):
            try:
                out[key] = EnvVar(**value)
            except Exception as exc:  # pydantic ValidationError
                raise AgentPackError(
                    AP1003, f"{where}: invalid declaration for '{key}': {exc}"
                ) from exc
        else:
            raise AgentPackError(AP1003, f"{where}: '{key}' must be a string or mapping")
    return out


def load_mcp_server(path: Path, diags: Diagnostics) -> MCPServer:
    data = _read_yaml(path)
    if data.get("kind") not in (None, "MCPServer"):
        raise AgentPackError(AP1003, f"{path.name}: kind must be 'MCPServer'")

    meta = data.get("metadata") or {}
    name = meta.get("name") or path.stem
    transport = TransportType(str((data.get("transport") or {}).get("type", "stdio")))

    command = None
    endpoint = None
    if transport is TransportType.STDIO:
        cmd = data.get("command") or {}
        if not cmd.get("executable"):
            raise AgentPackError(
                AP1003, f"{path.name}: stdio transport requires command.executable"
            )
        command = Command(**cmd)
    else:
        ep = data.get("endpoint") or {}
        if not ep.get("url"):
            raise AgentPackError(AP1003, f"{path.name}: {transport.value} requires endpoint.url")
        endpoint = Endpoint(**ep)

    server = MCPServer(
        name=name,
        displayName=meta.get("displayName"),
        description=meta.get("description", ""),
        transport=transport,
        command=command,
        endpoint=endpoint,
        headers=_env_map(data.get("headers"), path.name),
        environment=_env_map(data.get("environment"), path.name),
        capabilities=MCPCapabilities(**(data.get("capabilities") or {})),
        source_file=path,
    )
    for key, var in server.user_inputs().items():
        if var.secret and var.value:
            diags.error(AP1003, f"secret '{key}' must not carry a value", source=str(path))
    return server


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------
def _collect_assets(project_dir: Path, entries: list[Any], kind: str) -> list[FileAsset]:
    out: list[FileAsset] = []
    for entry in entries:
        raw = entry.get("path") if isinstance(entry, dict) else entry
        base = ensure_inside(project_dir, project_dir / str(raw))
        if base.is_file():
            out.append(
                FileAsset(
                    name=base.stem, kind=kind, source=base, relative_path=base.name
                )
            )
        elif base.is_dir():
            for rel in iter_files(base):
                out.append(
                    FileAsset(
                        name=rel.stem,
                        kind=kind,
                        source=base / rel,
                        relative_path=str(rel).replace("\\", "/"),
                    )
                )
    return out


def _load_includes(
    project_dir: Path,
    entries: list[Any],
    diags: Diagnostics,
    seen: set[Path],
) -> list[AgentPackage]:
    """Compose other AgentPack projects by reference.

    Each producing repository keeps its own ``agentpack.yaml`` as the single
    definition of what it ships; an aggregator points at those manifests instead
    of re-listing their contents.
    """
    out: list[AgentPackage] = []
    for entry in entries:
        raw = entry.get("path") if isinstance(entry, dict) else entry
        candidate = (project_dir / str(raw)).resolve()
        child_dir = candidate.parent if candidate.is_file() else candidate

        if not child_dir.is_dir():
            diags.error(AP1007, f"include path not found: {raw}")
            continue
        try:
            child_manifest = manifest_path(child_dir)
        except AgentPackError:
            diags.error(AP1007, f"include '{raw}' has no agentpack.yaml")
            continue
        if child_manifest in seen:
            diags.error(AP1007, f"circular include: {raw}")
            continue
        if project_dir != child_dir and project_dir not in child_dir.parents:
            # Sibling checkouts are the normal multi-repo layout; still worth surfacing.
            diags.info(AP1007, f"include '{raw}' resolves outside the project root")

        child = load_package(child_manifest, diags, seen)
        diags.info(
            AP1007,
            f"included {child.metadata.name} {child.metadata.version}: "
            f"{len(child.skills)} skill(s), {len(child.mcp_servers)} MCP server(s)",
        )
        out.append(child)
    return out


def load_package(
    source: Path,
    diags: Diagnostics | None = None,
    _seen: set[Path] | None = None,
) -> AgentPackage:
    """Load a project from a manifest file, or from a directory containing one.

    Every path inside the manifest is resolved relative to the manifest's own
    directory, which becomes the project root.
    """
    diags = diags if diags is not None else Diagnostics()
    manifest = resolve_manifest(source)
    project_dir = manifest.parent
    seen = _seen if _seen is not None else set()
    seen.add(manifest)
    data = _read_yaml(manifest)

    api = data.get("apiVersion")
    if api != API_VERSION:
        diags.warning(AP1001, f"apiVersion '{api}' differs from supported '{API_VERSION}'")
    if data.get("kind") not in (None, "AgentPackage"):
        raise AgentPackError(AP1001, "kind must be 'AgentPackage'")
    if "metadata" not in data:
        raise AgentPackError(AP1001, "manifest is missing 'metadata'")

    metadata = PackageMetadata(**data["metadata"])

    included = _load_includes(project_dir, data.get("include") or [], diags, seen)

    skills: list[Skill] = []
    for entry in data.get("skills") or []:
        raw = entry.get("path") if isinstance(entry, dict) else entry
        path = ensure_inside(project_dir, project_dir / str(raw))
        candidates, archives = _skill_candidates(path)
        if not candidates and not archives:
            diags.error(AP1002, f"skill path not found: {raw}")
            continue
        for cand in candidates:
            skill = load_skill(cand, diags)
            if skill:
                skills.append(skill)
        for archive in archives:
            skills.extend(load_skill_zip(archive, diags))

    servers: list[MCPServer] = []
    for entry in data.get("mcp") or []:
        raw = entry.get("path") if isinstance(entry, dict) else entry
        path = ensure_inside(project_dir, project_dir / str(raw))
        files = (
            [path]
            if path.is_file()
            else sorted(p for p in path.glob("*.y*ml"))
            if path.is_dir()
            else []
        )
        if not files:
            diags.error(AP1003, f"mcp path not found: {raw}")
        for f in files:
            servers.append(load_mcp_server(f, diags))
    desktop_mcpb: list[Path] = []
    for raw in data.get("claudeDesktopMcpb") or []:
        path = ensure_inside(project_dir, project_dir / str(raw))
        if not path.is_file() or path.suffix.lower() != ".mcpb":
            diags.error(AP1003, f"Claude Desktop MCPB not found: {raw}")
            continue
        desktop_mcpb.append(path)
    assets: dict[str, list[FileAsset]] = {
        key: _collect_assets(project_dir, data.get(key) or [], kind)
        for key, kind in _ASSET_KINDS.items()
    }

    for child in included:
        skills.extend(child.skills)
        servers.extend(child.mcp_servers)
        assets["prompts"].extend(child.prompts)
        assets["agents"].extend(child.agents)
        assets["commands"].extend(child.commands)
        assets["hooks"].extend(child.hooks)
        assets["assets"].extend(child.assets)

    build_raw = dict(data.get("build") or {})
    compat = (data.get("compatibility") or {}).get("unsupportedFeaturePolicy", "warn")

    targets = [str(target) for target in (data.get("targets") or [])]
    normalized_targets: list[str] = []
    for target in targets:
        normalized = _TARGET_ALIASES.get(target, target)
        if normalized != target:
            diags.warning(
                AP2001,
                f"target '{target}' now builds the host-neutral '{normalized}' plugin",
            )
        if normalized not in normalized_targets:
            normalized_targets.append(normalized)

    return AgentPackage(
        metadata=metadata,
        targets=normalized_targets,
        skills=sorted(skills, key=lambda s: s.name),
        mcp_servers=sorted(servers, key=lambda s: s.name),
        claude_desktop_mcpb=sorted(desktop_mcpb),
        prompts=assets["prompts"] + assets["instructions"],
        agents=assets["agents"],
        commands=assets["commands"],
        hooks=assets["hooks"],
        assets=assets["assets"],
        build=BuildOptions(**build_raw),
        compatibility_policy=UnsupportedFeaturePolicy(compat),
        target_options=data.get("targetOptions") or {},
        target_raw=data.get("targetRaw") or {},
        project_dir=project_dir,
    )
