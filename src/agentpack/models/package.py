"""Canonical, normalized data model.

Adapters only ever receive :class:`AgentPackage`; they never read the source
tree directly. That keeps target-specific logic out of the loader.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SEMVER_HINT = "MAJOR.MINOR.PATCH"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------
class Author(StrictModel):
    name: str
    email: str | None = None
    url: str | None = None


class PackageMetadata(StrictModel):
    name: str
    version: str = "0.1.0"
    display_name: str | None = Field(default=None, alias="displayName")
    description: str = ""
    license: str | None = None
    homepage: str | None = None
    repository: str | None = None
    keywords: list[str] = Field(default_factory=list)
    authors: list[Author] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError("name must be a slug of [A-Za-z0-9-_.]")
        return v

    @property
    def title(self) -> str:
        return self.display_name or self.name

    @property
    def author_name(self) -> str:
        return self.authors[0].name if self.authors else "unknown"


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------
class Skill(StrictModel):
    """An Agent Skill (SKILL.md + optional supporting files).

    Source skills can be ordinary directories or a skill root inside a ZIP.
    ZIPs are consumed as source material only; generated artifacts always
    contain the normal unpacked ``<skill>/SKILL.md`` layout.
    """

    name: str
    description: str = ""
    version: str | None = None
    source_dir: Path
    skill_md: Path
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""
    files: list[Path] = Field(default_factory=list)
    """Paths relative to ``source_dir``, excluding SKILL.md. Sorted."""
    source_archive: Path | None = None
    """ZIP source when the skill was supplied as an archive."""
    archive_root: str = ""
    """POSIX path to the skill root within ``source_archive`` (empty at ZIP root)."""

    @property
    def has_references(self) -> bool:
        return any(str(p).replace("\\", "/").startswith("references/") for p in self.files)


class KnowledgeMode(str, Enum):
    """How a skill's supporting corpus reaches the client.

    Lesson from rad-agent-toolkit: this is a *deployment* decision, not a
    skill-authoring one. The same SKILL.md ships in both modes and the mode is
    stamped into the artifact so a runtime version check can detect drift.
    """

    SERVED = "served"  # default: strip references/; an MCP server serves them at runtime
    BUNDLED = "bundled"  # ship references/ inside the skill


SERVED_STAMP = "<!--agentpack-mode:served-->"


# --------------------------------------------------------------------------
# MCP servers
# --------------------------------------------------------------------------
class EnvVarSource(str, Enum):
    USER = "user"  # prompted / filled in by the installing user
    LITERAL = "literal"  # constant, optionally a target-scoped stored secret


class EnvVar(StrictModel):
    source: EnvVarSource = EnvVarSource.USER
    value: str | None = None
    required: bool = True
    secret: bool = False
    description: str = ""
    type: Literal["string", "file", "directory", "number", "boolean"] = "string"
    default: str | None = None
    title: str | None = None

class TransportType(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class Command(StrictModel):
    executable: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None


class Endpoint(StrictModel):
    url: str


class MCPCapabilities(StrictModel):
    tools: bool = True
    resources: bool = False
    prompts: bool = False


class MCPServer(StrictModel):
    name: str
    display_name: str | None = Field(default=None, alias="displayName")
    description: str = ""
    transport: TransportType = TransportType.STDIO
    command: Command | None = None
    endpoint: Endpoint | None = None
    headers: dict[str, EnvVar] = Field(default_factory=dict)
    environment: dict[str, EnvVar] = Field(default_factory=dict)
    capabilities: MCPCapabilities = Field(default_factory=MCPCapabilities)
    source_file: Path | None = None

    @property
    def is_remote(self) -> bool:
        return self.transport in (TransportType.HTTP, TransportType.SSE)

    def user_inputs(self) -> dict[str, EnvVar]:
        """Every value the end user must supply after install."""
        out = {k: v for k, v in self.environment.items() if v.source is EnvVarSource.USER}
        out.update({k: v for k, v in self.headers.items() if v.source is EnvVarSource.USER})
        return out


# --------------------------------------------------------------------------
# Other capability types
# --------------------------------------------------------------------------
class FileAsset(StrictModel):
    """A prompt, instruction, agent, command, hook or plain asset file."""

    name: str
    kind: Literal["prompt", "instruction", "agent", "command", "hook", "asset"]
    source: Path
    relative_path: str


# --------------------------------------------------------------------------
# Package
# --------------------------------------------------------------------------
class UnsupportedFeaturePolicy(str, Enum):
    IGNORE = "ignore"
    WARN = "warn"
    ERROR = "error"


class BuildOptions(StrictModel):
    output: str = "dist"
    clean: bool = True
    reproducible: bool = True
    knowledge: KnowledgeMode = KnowledgeMode.SERVED


class AgentPackage(StrictModel):
    """The normalized model handed to every adapter."""

    metadata: PackageMetadata
    targets: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    mcp_servers: list[MCPServer] = Field(default_factory=list)
    claude_desktop_mcpb: list[Path] = Field(default_factory=list)
    prompts: list[FileAsset] = Field(default_factory=list)
    agents: list[FileAsset] = Field(default_factory=list)
    commands: list[FileAsset] = Field(default_factory=list)
    hooks: list[FileAsset] = Field(default_factory=list)
    assets: list[FileAsset] = Field(default_factory=list)
    build: BuildOptions = Field(default_factory=BuildOptions)
    compatibility_policy: UnsupportedFeaturePolicy = UnsupportedFeaturePolicy.WARN
    target_options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    target_raw: dict[str, dict[str, Any]] = Field(default_factory=dict)
    project_dir: Path = Path(".")

    def options_for(self, target: str) -> dict[str, Any]:
        return self.target_options.get(target, {})

    def raw_for(self, target: str) -> dict[str, Any]:
        return self.target_raw.get(target, {})


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------
class Support(str, Enum):
    FULL = "true"
    PARTIAL = "partial"
    NONE = "false"


class ArtifactType(str, Enum):
    PLUGIN = "plugin"
    EXTENSION = "extension"
    BUNDLE = "bundle"
    ARCHIVE = "archive"
    MANIFEST = "manifest"
    CONFIG_EXPORT = "configuration-export"
    MARKETPLACE_PACKAGE = "marketplace-package"


class TargetCapabilities(StrictModel):
    skills: Support = Support.NONE
    mcp_stdio: Support = Support.NONE
    mcp_http: Support = Support.NONE
    user_config: Support = Support.NONE
    """Can the target prompt the user for secrets at install time?"""
    prompts: Support = Support.NONE
    agents: Support = Support.NONE
    commands: Support = Support.NONE
    hooks: Support = Support.NONE
    artifact_type: ArtifactType = ArtifactType.CONFIG_EXPORT
    experimental: bool = False
    spec_version: str | None = None
    last_verified: str | None = None
    notes: str = ""


class ArchiveSpec(StrictModel):
    """A sub-directory that becomes its own distributable archive."""

    root: str
    label: str
    suffix: str = ".zip"
    source_is_file: bool = False
    filename: str | None = None


class BuildResult(StrictModel):
    target: str
    output_dir: Path
    artifact_type: ArtifactType
    files: list[str] = Field(default_factory=list)
    archive_specs: list[ArchiveSpec] = Field(default_factory=list)
    """Empty means the whole target directory becomes one archive."""
    archives: list[Path] = Field(default_factory=list)
