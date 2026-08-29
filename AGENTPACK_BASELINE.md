# AgentPack — Repository Baseline

> **Working name:** AgentPack  
> **Purpose:** Define AI capabilities once, then build portable, client-specific plugin/import packages for multiple AI clients without directly installing files into client-native configuration directories.

---

## 0. Implementation status

This document is the original design baseline. The MVP described in §42 is
implemented; where reality differed from the sketch, the code and the docs below
are authoritative:

| Baseline section | Status | Where |
|---|---|---|
| CLI (§6, §7) | done — `init`, `validate`, `inspect`, `build`, `package`, `list-targets`, `clean`, `doctor`, `version` | `src/agentpack/cli.py` |
| Canonical manifest (§8) | done | [docs/manifest.md](docs/manifest.md) |
| Canonical MCP schema (§9) | done | [docs/mcp-schema.md](docs/mcp-schema.md) |
| Secrets (§10) | done — never embedded; mapped per target | [docs/mcp-schema.md](docs/mcp-schema.md) |
| Internal model (§13) | done | `src/agentpack/models/package.py` |
| Adapter API + registry (§14, §15, §33) | done, incl. `agentpack.targets` entry points | `src/agentpack/core/registry.py` |
| Capability matrix (§16) | done, live via `list-targets -v` | [docs/compatibility.md](docs/compatibility.md) |
| Adapters (§17) | `claude-desktop`, `claude-code`, `copilot-vscode`, `copilot-intellij`, `codex`, `universal` | [docs/adapters.md](docs/adapters.md) |
| Diagnostics (§21) | done, stable codes | `src/agentpack/core/diagnostics.py` |
| Build pipeline (§23) | done, staging + atomic promotion | `src/agentpack/core/builder.py` |
| Determinism (§5.4) | done, SHA-256 per target in the build manifest | `src/agentpack/core/builder.py` |
| Security (§28) | done — no execution, no symlinks, no traversal, no local secrets | [docs/architecture.md](docs/architecture.md) |
| Build vs package (§48) | done — `dist/build/` and `dist/packages/` | — |

Deviations worth noting:

- **Target names are client-specific**, not vendor-specific: `claude-desktop`
  and `claude-code` are separate adapters because their formats share nothing.
  Likewise `copilot-vscode` vs `copilot-intellij`.
- **Knowledge modes** (`bundled` / `served`) were added to the model. Large
  skills carry a `references/` corpus, and whether it ships with the skill or is
  served by an MCP server at runtime is a deployment decision. See the README.
- **Artifact type is enforced product vocabulary** (§45, §46): only
  `claude-desktop` and `claude-code` are plugin/bundle grade today; the rest are
  honestly labelled `configuration-export`.

---

## 1. Product Vision

AgentPack is a cross-client packaging and build tool for AI agent capabilities.

The user maintains one canonical project containing:

- Agent Skills
- MCP server definitions
- prompts / instructions
- optional agents / subagents
- optional commands
- optional hooks
- package metadata

AgentPack converts that canonical project into distributable artifacts for supported AI clients.

The generated artifacts are intended to be:

- downloaded
- shared
- versioned
- published
- imported
- installed by the end user through the target AI client's supported UI, extension manager, plugin mechanism, or documented import process

AgentPack should **not** directly modify the target user's native AI-client configuration directories as its primary workflow.

---

## 2. Core Idea

```text
                     AgentPack Project
                           │
              ┌────────────┴────────────┐
              │                         │
           Skills                    MCPs
         SKILL.md              canonical definitions
              │                         │
              └────────────┬────────────┘
                           │
                    agentpack build
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
      Claude            Copilot            Codex
      package           package            package
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                    Other AI clients
```

The key philosophy is:

> **Author once. Package for many AI clients.**

---

## 3. Non-Goals

For the initial project, AgentPack is **not**:

- an AI agent runtime
- an MCP server runtime
- an LLM proxy
- a model router
- an MCP marketplace
- a Skills marketplace
- a replacement for the target AI client's UI
- a background daemon
- an automatic installer into `~/.claude`, `~/.codex`, `~/.copilot`, etc.
- a secrets manager
- a workflow orchestration engine like LangGraph

Some of these may later integrate with AgentPack, but they are outside the MVP.

---

## 4. Primary User Story

A developer creates:

```text
my-agent-package/
├── agentpack.yaml
├── skills/
│   ├── network-analysis/
│   │   └── SKILL.md
│   └── incident-report/
│       └── SKILL.md
├── mcp/
│   ├── github.yaml
│   └── monitoring.yaml
└── assets/
```

Then runs:

```bash
agentpack build
```

AgentPack produces:

```text
dist/
├── claude/
├── copilot/
├── codex/
├── cursor/
├── gemini/
└── universal/
```

Each directory contains the target-specific files necessary for the user to install/import the capabilities into that AI client.

---

## 5. Design Principles

### 5.1 Canonical source, generated outputs

The source project is the authority.

Generated client files should not normally be edited manually.

```text
Canonical source
      ↓
Normalized internal model
      ↓
Target adapter
      ↓
Generated client package
```

---

### 5.2 Never lose semantics silently

If a target client cannot support a source feature, AgentPack must not silently ignore it.

It should:

1. map it if possible
2. downgrade it if explicitly allowed
3. emit a warning
4. fail in strict mode

Example:

```text
WARNING AP2301:
Target "foo-client" does not support hooks.
2 hooks were omitted.
```

---

### 5.3 Client adapters must be isolated

Every target format should be implemented as an adapter.

Core build logic must not contain target-specific conditionals everywhere.

Bad:

```python
if target == "claude":
    ...
elif target == "copilot":
    ...
```

Preferred:

```python
adapter = registry.get(target)
adapter.validate(model)
adapter.build(model, output_dir)
```

---

### 5.4 Deterministic builds

Given the same source and AgentPack version, build output should be deterministic whenever possible.

This enables:

- Git diffs
- CI
- reproducible releases
- package signing later
- checksum verification

---

### 5.5 Inspect before build

The tool should expose a normalized representation before generating files.

```bash
agentpack inspect
```

This is important for debugging mappings between formats.

---

## 6. Proposed CLI

Initial CLI:

```bash
agentpack init
agentpack validate
agentpack inspect
agentpack build
agentpack list-targets
agentpack doctor
agentpack clean
agentpack version
```

Optional later commands:

```bash
agentpack package
agentpack publish
agentpack diff
agentpack migrate
agentpack schema
agentpack verify
agentpack sign
agentpack import
```

---

## 7. CLI Examples

### Initialize a project

```bash
agentpack init my-agent-package
```

Expected output:

```text
my-agent-package/
├── agentpack.yaml
├── skills/
├── mcp/
├── prompts/
├── assets/
└── .gitignore
```

---

### Validate

```bash
agentpack validate
```

Example:

```text
✓ agentpack.yaml valid
✓ 2 skills found
✓ 2 MCP definitions valid
✓ target claude supported
✓ target copilot supported
✓ target codex supported

Validation successful.
```

---

### Build all configured targets

```bash
agentpack build
```

---

### Build selected targets

```bash
agentpack build --target claude
```

```bash
agentpack build --target claude --target copilot --target codex
```

---

### Strict mode

```bash
agentpack build --strict
```

Any unsupported feature causes the build to fail.

---

### Inspect normalized model

```bash
agentpack inspect --format yaml
```

or:

```bash
agentpack inspect --format json
```

---

### List supported targets

```bash
agentpack list-targets
```

Example:

```text
claude
copilot
codex
cursor
gemini
universal
```

---

## 8. Canonical Project Manifest

Recommended filename:

```text
agentpack.yaml
```

Example:

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage

metadata:
  name: network-operations
  displayName: Network Operations Toolkit
  version: 0.1.0
  description: Skills and MCP integrations for network operations.
  license: Apache-2.0
  homepage: https://example.com
  repository: https://github.com/example/network-operations
  authors:
    - name: Example Team

targets:
  - claude
  - copilot
  - codex
  - cursor
  - gemini
  - universal

skills:
  - path: skills/network-analysis
  - path: skills/incident-report

mcp:
  - path: mcp/github.yaml
  - path: mcp/monitoring.yaml

prompts:
  - path: prompts/

assets:
  - path: assets/

build:
  output: dist
  clean: true
  reproducible: true

compatibility:
  unsupportedFeaturePolicy: warn
```

---

## 9. Canonical MCP Definition

AgentPack should maintain its own normalized MCP representation.

Example:

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer

metadata:
  name: github

transport:
  type: stdio

command:
  executable: npx
  args:
    - "-y"
    - "@example/github-mcp"

environment:
  GITHUB_TOKEN:
    source: user
    required: true
    secret: true
    description: GitHub personal access token

capabilities:
  tools: true
  resources: true
  prompts: false
```

Another example:

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer

metadata:
  name: monitoring

transport:
  type: http

endpoint:
  url: https://mcp.example.com

headers:
  Authorization:
    source: user
    required: true
    secret: true
```

---

## 10. Secrets

Secrets must **never** be embedded into generated packages by default.

Canonical definitions may declare required secret inputs.

Example:

```yaml
environment:
  API_TOKEN:
    source: user
    required: true
    secret: true
```

Target adapters should convert this into the closest supported target-client mechanism.

If the client supports interactive configuration, generate metadata describing the required field.

If not, generate:

- placeholder values
- setup instructions
- warnings

Never copy local environment secret values unless an explicit future opt-in mechanism is designed.

---

## 11. Skills

AgentPack should support Agent Skills as directory-based units.

Recommended structure:

```text
skills/
└── network-analysis/
    ├── SKILL.md
    ├── scripts/
    ├── references/
    └── assets/
```

At minimum, preserve:

- `SKILL.md`
- skill directory hierarchy
- supporting scripts
- supporting files
- references
- assets

AgentPack should not rewrite skill content unnecessarily.

---

## 12. Optional Capability Types

Architecture should allow these to be added later:

```text
skills/
mcp/
agents/
commands/
hooks/
prompts/
instructions/
workflows/
assets/
```

Internal representation should therefore use a general package model rather than hard-coding only Skills + MCP forever.

---

## 13. Internal Data Model

Suggested conceptual model:

```text
AgentPackage
│
├── metadata
├── skills[]
├── mcpServers[]
├── prompts[]
├── agents[]
├── commands[]
├── hooks[]
├── assets[]
├── targetOptions{}
└── compatibilityPolicy
```

Python-like representation:

```python
class AgentPackage:
    metadata: PackageMetadata
    skills: list[Skill]
    mcp_servers: list[MCPServer]
    prompts: list[Prompt]
    agents: list[Agent]
    commands: list[Command]
    hooks: list[Hook]
    assets: list[Asset]
```

The exact implementation language is open, but adapters should only receive this normalized model.

---

## 14. Adapter Interface

Conceptual interface:

```python
class TargetAdapter:
    name: str

    def capabilities(self) -> TargetCapabilities:
        ...

    def validate(self, package: AgentPackage) -> list[Diagnostic]:
        ...

    def build(
        self,
        package: AgentPackage,
        output_dir: Path
    ) -> BuildResult:
        ...
```

Possible additional methods:

```python
detect_version()
generate_manifest()
generate_readme()
package_archive()
validate_output()
```

---

## 15. Adapter Registry

Adapters should register by target name.

Concept:

```python
registry.register("claude", ClaudeAdapter())
registry.register("copilot", CopilotAdapter())
registry.register("codex", CodexAdapter())
registry.register("cursor", CursorAdapter())
registry.register("gemini", GeminiAdapter())
registry.register("universal", UniversalAdapter())
```

Then:

```python
adapter = registry.get(target)
```

Future third-party adapters should be possible.

---

## 16. Target Capability Matrix

Maintain a machine-readable capability model.

Example:

```yaml
targets:
  claude:
    skills: true
    mcp: true
    agents: true
    commands: true
    hooks: true

  copilot:
    skills: true
    mcp: true
    agents: partial
    commands: partial
    hooks: false

  codex:
    skills: true
    mcp: true
    agents: partial
    commands: false
    hooks: false
```

**Important:** Actual values must be verified against current official target documentation before implementation.

Do not assume this sample matrix is authoritative.

---

## 17. Target Adapters

Initial adapter candidates:

```text
claude
copilot
codex
cursor
gemini
universal
```

Potential later adapters:

```text
cline
windsurf
roo
opencode
zed
jetbrains
mcpb
```

Each adapter should document:

- supported capabilities
- generated files
- packaging structure
- expected installation/import mechanism
- unsupported capabilities
- target-specific options
- target-client minimum version if applicable

---

## 18. Universal Adapter

Where an open/common Agent Plugin standard is available, AgentPack should support it as a first-class target.

Example:

```bash
agentpack build --target universal
```

Output might resemble:

```text
dist/universal/
├── plugin.json
├── skills/
├── mcp/
└── README.md
```

The exact schema must be implemented from the current official specification.

Do not invent unsupported fields.

---

## 19. Generated Documentation

Every target output should include human-readable install instructions when useful.

Example:

```text
dist/claude/README.md
dist/copilot/README.md
dist/codex/README.md
```

The README should explain:

- what the artifact contains
- supported client/version
- how to import/install it using the client
- required environment variables
- required secrets
- post-install validation
- known limitations

This makes generated output usable even when clients differ in UI behavior.

---

## 20. Build Manifest

Every build should produce metadata such as:

```text
dist/agentpack-build.json
```

Example:

```json
{
  "agentpackVersion": "0.1.0",
  "package": "network-operations",
  "packageVersion": "0.1.0",
  "targets": [
    "claude",
    "copilot",
    "codex"
  ],
  "artifacts": []
}
```

Possible later additions:

- hashes
- signatures
- timestamps
- source Git commit
- SBOM reference

For reproducibility, timestamps should be optional or normalized.

---

## 21. Diagnostics

Diagnostics should have stable codes.

Example:

```text
AP1001 Invalid manifest
AP1002 Missing skill
AP1003 Invalid MCP definition

AP2001 Unsupported target
AP2101 Unsupported skill feature
AP2201 Unsupported MCP transport
AP2301 Unsupported hook

AP3001 Build failed
AP3002 Output validation failed
```

Format:

```text
WARNING AP2301 [copilot]:
Hook "pre-run" is not supported by this target.
```

Stable diagnostic codes help:

- documentation
- CI
- IDE integration
- AI coding agents
- bug reports

---

## 22. Validation Layers

Validation should happen in stages:

```text
Schema validation
       ↓
Source validation
       ↓
Semantic validation
       ↓
Target compatibility validation
       ↓
Generated output validation
```

### Schema validation

Check YAML/JSON structure.

### Source validation

Check referenced files exist.

### Semantic validation

Examples:

- duplicate skill names
- duplicate MCP names
- invalid versions
- missing metadata
- invalid environment declarations

### Target compatibility validation

Check whether requested capabilities can be represented.

### Output validation

Validate target manifests against target schemas where available.

---

## 23. Build Pipeline

Recommended flow:

```text
1. Discover project
2. Load agentpack.yaml
3. Validate canonical manifest
4. Load Skills
5. Load MCP definitions
6. Load optional capabilities
7. Create normalized package model
8. Validate normalized model
9. Resolve target adapters
10. Check compatibility
11. Build each target in temporary directory
12. Validate generated target files
13. Move successful artifacts into dist/
14. Generate build manifest
15. Print summary
```

Use temporary/staging directories so partially failed builds do not leave misleading output.

---

## 24. Recommended Repository Layout

```text
agentpack/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── pyproject.toml
│
├── docs/
│   ├── architecture.md
│   ├── manifest.md
│   ├── mcp-schema.md
│   ├── adapters.md
│   ├── compatibility.md
│   └── development.md
│
├── schemas/
│   ├── agentpack.schema.json
│   └── mcp-server.schema.json
│
├── src/
│   └── agentpack/
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── core/
│       │   ├── loader.py
│       │   ├── validator.py
│       │   ├── builder.py
│       │   ├── diagnostics.py
│       │   └── registry.py
│       │
│       ├── models/
│       │   ├── package.py
│       │   ├── skill.py
│       │   ├── mcp.py
│       │   └── target.py
│       │
│       └── adapters/
│           ├── base.py
│           ├── claude/
│           ├── copilot/
│           ├── codex/
│           ├── cursor/
│           ├── gemini/
│           └── universal/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── golden/
│
└── examples/
    ├── minimal/
    ├── skills-only/
    ├── mcp-only/
    └── full-package/
```

This baseline assumes Python for the first implementation because it is fast to develop and suitable for AI-assisted coding.

Changing implementation language later should not change the conceptual architecture.

---

## 25. Golden Tests

Target adapters should rely heavily on golden/snapshot tests.

Example:

```text
tests/golden/
└── minimal/
    ├── claude/
    ├── copilot/
    ├── codex/
    └── universal/
```

Test:

```text
canonical fixture
      ↓
adapter build
      ↓
generated directory
      ↓
compare with expected golden directory
```

This is extremely important because target formats will evolve.

---

## 26. Unit Tests

Test at least:

- manifest parsing
- invalid manifest handling
- MCP parsing
- skill discovery
- duplicate detection
- target registry
- unsupported target handling
- compatibility warnings
- strict mode
- deterministic output
- clean build behavior
- secret redaction
- output path safety

---

## 27. Integration Tests

For every adapter:

```text
load fixture
build target
validate generated tree
validate manifest
verify expected capability mappings
verify warnings
```

Where official validation tools exist, use them in CI if practical.

---

## 28. Security Requirements

AgentPack processes potentially executable content.

Security requirements:

- never execute skill scripts during build
- never execute MCP commands during build
- never automatically run generated packages
- never interpolate arbitrary shell expressions
- never collect local secrets automatically
- sanitize archive paths
- reject path traversal such as `../../`
- validate symlinks
- avoid writing outside configured output directory
- redact secret values from logs
- treat source repository contents as untrusted
- verify downloaded remote schemas before relying on them
- pin dependencies appropriately

Later:

- signing
- checksums
- provenance
- SBOM
- package trust policy

---

## 29. Remote Sources

Not MVP.

Future syntax could support:

```yaml
skills:
  - git:
      repository: https://github.com/example/skills
      ref: v1.2.0
      path: skills/network
```

Do not implement remote fetching in the earliest MVP unless needed.

Local sources are safer and easier.

---

## 30. Package Dependencies

Future feature.

Example:

```yaml
dependencies:
  - package: example/common-skills
    version: "^1.2"
```

This would eventually require:

- dependency resolution
- lockfile
- package registry or Git references
- conflict handling
- transitive dependency policy

Potential lockfile:

```text
agentpack.lock
```

Not required for MVP.

---

## 31. Target-Specific Overrides

Some target differences cannot be abstracted cleanly.

Allow explicit overrides.

Example:

```yaml
targetOptions:

  claude:
    displayName: Network Operations

  copilot:
    category: developer-tools

  codex:
    experimental: false
```

Rules:

1. canonical model first
2. generic mapping second
3. explicit target override last

Avoid forcing users to duplicate the entire target manifest.

---

## 32. Escape Hatch

For unsupported target-specific fields, future versions may expose:

```yaml
targetRaw:
  claude:
    someNativeField: value
```

Use sparingly.

This prevents AgentPack from becoming a blocker when client schemas evolve faster than AgentPack.

---

## 33. Plugin Adapter SDK

Later, third parties should be able to implement external adapters.

Concept:

```text
agentpack-adapter-jetbrains
agentpack-adapter-company-x
```

Possible entry-point architecture:

```python
agentpack.targets
```

The core project should therefore avoid importing every adapter directly.

---

## 34. Versioning

AgentPack itself:

```text
Semantic Versioning
MAJOR.MINOR.PATCH
```

Canonical schema:

```yaml
apiVersion: agentpack.dev/v1alpha1
```

Schema evolution should be independent from CLI version.

Possible future stages:

```text
v1alpha1
v1alpha2
v1beta1
v1
```

---

## 35. Compatibility Tracking

Client formats can evolve quickly.

Each adapter should have metadata:

```yaml
target: claude
adapterVersion: 1
testedClientVersions:
  - "..."
specVersion: "..."
lastVerified: "..."
```

Do not hardcode unverifiable version numbers.

Maintain this data from official documentation and automated tests where possible.

---

## 36. CI

Recommended initial GitHub Actions jobs:

```text
lint
type-check
unit-tests
integration-tests
schema-tests
golden-tests
build-package
```

Later:

```text
adapter-conformance
security-scan
dependency-scan
release
sign-artifacts
```

---

## 37. Release Artifacts

Potential releases:

```text
agentpack executable
Python package
Homebrew package
Windows executable
Linux binary/package
container image
```

Do not make container usage mandatory.

A local CLI should be the primary developer experience.

---

## 38. Recommended Initial Technology

Suggested MVP stack:

```text
Language: Python 3.11+
CLI: Typer
Models / validation: Pydantic
YAML: PyYAML or ruamel.yaml
JSON Schema: jsonschema
Testing: pytest
Packaging: hatchling / uv / standard pyproject
Linting: Ruff
Typing: mypy or pyright
```

This is a recommendation, not a hard architectural requirement.

Prefer simple dependencies.

---

## 39. Example MVP Manifest

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: AgentPackage

metadata:
  name: demo
  version: 0.1.0
  description: AgentPack demo package

targets:
  - universal
  - claude

skills:
  - path: skills/example

mcp:
  - path: mcp/example.yaml
```

---

## 40. Example Skill

```text
skills/example/SKILL.md
```

Example content:

```markdown
---
name: example
description: Example AgentPack skill.
---

# Example Skill

Use this skill when the user requests an example operation.
```

AgentPack should treat the file as source content and preserve it.

---

## 41. Example MCP

```text
mcp/example.yaml
```

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer

metadata:
  name: example

transport:
  type: stdio

command:
  executable: example-mcp
  args: []

environment:
  EXAMPLE_TOKEN:
    source: user
    required: true
    secret: true
```

---

## 42. MVP Scope

### MVP 0.1

Implement:

- `agentpack init`
- `agentpack validate`
- `agentpack inspect`
- `agentpack build`
- `agentpack list-targets`
- canonical `agentpack.yaml`
- canonical MCP schema
- local Skills
- local MCP definitions
- normalized model
- adapter API
- 2 real target adapters
- universal adapter if official spec is stable enough
- deterministic output
- warnings
- strict mode
- generated installation README
- unit tests
- golden adapter tests

Do not implement:

- registry
- marketplace
- dependency resolution
- package signing
- remote Skill repositories
- GUI
- automatic installation
- cloud service
- telemetry by default

---

## 43. Suggested First Adapters

Implementation priority should be based on:

1. stable official specification
2. ability to create a portable artifact
3. UI/import/install support
4. user demand
5. quality of validation tooling

Suggested investigation order:

```text
1. Universal / open Agent Plugin format
2. Claude
3. GitHub Copilot
4. Codex
5. Cursor
6. Gemini
```

Do not implement based only on assumptions.

Before implementing each adapter, the coding agent must inspect the latest official target documentation.

---

## 44. Adapter Research Checklist

Before writing an adapter, answer:

```text
[ ] What is the official plugin/package format?
[ ] Is the format documented publicly?
[ ] Is there a JSON Schema?
[ ] Can Skills be packaged?
[ ] Can MCP servers be packaged?
[ ] Can MCP user configuration/secrets be declared?
[ ] Is there a package manifest?
[ ] Is there an archive format?
[ ] Can users install/import through UI?
[ ] Is installation local, marketplace-based, or both?
[ ] Does the target support update/versioning?
[ ] Can one package contain multiple Skills?
[ ] Can one package contain multiple MCP servers?
[ ] Are hooks supported?
[ ] Are agents/subagents supported?
[ ] Are commands supported?
[ ] Are prompts supported?
[ ] Are there naming restrictions?
[ ] Are there file size limits?
[ ] Is signing required?
[ ] Is a marketplace required?
[ ] Is there an official validator?
[ ] What target/client versions support it?
```

Record findings in:

```text
docs/targets/<target>.md
```

---

## 45. Definition of "Supported Target"

A target must not be marked supported merely because AgentPack can generate some config file.

A supported target should ideally satisfy:

```text
Canonical source
      ↓
AgentPack
      ↓
portable artifact
      ↓
target-supported user import/install workflow
```

If the only integration available is manual copying of native config files, mark the adapter clearly as:

```text
experimental
configuration-export-only
```

This distinction is central to AgentPack's product identity.

---

## 46. Artifact Types

AgentPack should describe outputs using explicit artifact types.

Possible values:

```text
plugin
extension
bundle
archive
manifest
configuration-export
marketplace-package
```

Example build summary:

```text
TARGET     TYPE        STATUS
claude     plugin      ✓
copilot    plugin      ✓
codex      bundle      ✓
legacy-x   config      ⚠ configuration-export-only
```

---

## 47. Update Strategy

AgentPack should generate artifacts that can participate in the target client's normal update mechanism where that mechanism exists.

AgentPack itself should not silently overwrite installed target-client files.

Potential metadata:

```yaml
metadata:
  name: network-operations
  version: 1.2.0
```

The generated package should preserve semantic version information whenever the target supports it.

---

## 48. Build vs Package

Potential command distinction:

```bash
agentpack build
```

Creates unpacked target directories.

```bash
agentpack package
```

Creates final distributable archives/packages.

Example:

```text
dist/
├── build/
│   ├── claude/
│   └── copilot/
│
└── packages/
    ├── network-operations-claude-1.0.0.zip
    └── network-operations-copilot-1.0.0.zip
```

For MVP, these can initially be one command if simpler.

---

## 49. Future GUI

A GUI may eventually sit on top of the same core library.

Possible workflow:

```text
Select Skills
      +
Configure MCPs
      +
Select targets
      ↓
Compatibility preview
      ↓
Build packages
      ↓
Download artifacts
```

The CLI/core architecture must remain usable independently.

---

## 50. Future Web Builder

Possible future service:

```text
AgentPack Web
```

User uploads or connects a repository.

UI displays:

```text
Skills detected: 5
MCP servers: 3

Targets:
[x] Claude
[x] Copilot
[x] Codex
[x] Cursor
[ ] Gemini

Compatibility:
Claude    100%
Copilot    90%
Codex      85%
```

Then:

```text
Build packages
```

This is not MVP.

---

## 51. Future AI-Assisted Migration

AgentPack could eventually help import an existing plugin:

```bash
agentpack import ./existing-claude-plugin
```

Then convert:

```text
Claude plugin
      ↓
normalized AgentPack source
      ↓
Copilot / Codex / Cursor / Gemini packages
```

AI may help with semantic transformations, but deterministic conversion should always be preferred where possible.

---

## 52. Future Diff

Useful command:

```bash
agentpack diff --target claude
```

Shows:

```text
canonical feature       target mapping
------------------------------------------------
skill/foo               supported
mcp/github              supported
hook/pre-run            unsupported
agent/reviewer          partial
```

This could become a major usability feature.

---

## 53. Future Compatibility Score

Potential output:

```text
Claude          100%
Copilot          92%
Codex            86%
Cursor           90%
Gemini           82%
```

Do not initially reduce compatibility to a misleading numeric score.

For MVP, explicit supported/partial/unsupported capability reporting is better.

---

## 54. Future Package Registry

Potential ecosystem:

```text
registry.agentpack.dev
```

Example:

```bash
agentpack add github:example/network-tools
```

But avoid building this until the packaging model is stable.

Git repositories themselves can serve as initial distribution.

---

## 55. Naming Conventions

CLI:

```text
agentpack
```

Manifest:

```text
agentpack.yaml
```

Schema namespace:

```text
agentpack.dev
```

Environment variables:

```text
AGENTPACK_*
```

Example:

```text
AGENTPACK_LOG_LEVEL
AGENTPACK_OUTPUT
```

Python package:

```text
agentpack
```

---

## 56. README One-Liner

Possible:

> **AgentPack packages Agent Skills, MCP servers, and agent capabilities into portable plugins for multiple AI clients.**

Alternative:

> **Define once. Package for every AI client.**

---

## 57. README Short Description

Suggested project description:

> AgentPack is an open-source build system for packaging Agent Skills, MCP server definitions, prompts, and other agent capabilities into portable, client-specific plugins and extensions. Maintain one canonical project and generate distributable artifacts for Claude, GitHub Copilot, Codex, Cursor, Gemini, and other AI clients without directly modifying client configuration directories.

---

## 58. Core Product Requirement

The following requirement must remain central:

> **AgentPack outputs files/packages that a user can take and install/import using the supported mechanisms of the target AI client.**

A feature that merely writes directly into an AI client's native configuration directory does **not** satisfy the primary AgentPack product requirement.

Configuration export may be supported as a fallback adapter type, but it must be identified clearly.

---

## 59. AI Coding Agent Instructions

When using an AI coding agent to implement this repository:

### Always

- read this baseline before architectural changes
- preserve adapter isolation
- prefer official client specifications
- verify current target formats before coding adapters
- write tests before or together with adapter implementation
- keep generated output deterministic
- keep source format independent from target formats
- update docs when schemas change
- update golden fixtures when adapter output intentionally changes
- preserve backwards compatibility where practical
- produce explicit diagnostics instead of silent omissions
- treat secrets carefully
- avoid automatic native-client installation behavior

### Never

- invent undocumented target manifest fields
- assume two clients use the same MCP format
- assume two clients use the same Skills format
- silently drop unsupported capabilities
- embed user secrets into artifacts
- execute MCP servers while building
- execute Skill scripts while building
- add target-specific logic to the generic model unless necessary
- couple the CLI directly to specific adapters
- make a cloud service mandatory
- make an LLM API mandatory for deterministic packaging

---

## 60. Coding Agent Task Pattern

For each implementation task, follow:

```text
1. Read baseline.
2. Identify affected architectural layer.
3. Inspect existing tests.
4. If target-specific:
      verify latest official specification.
5. Implement smallest coherent change.
6. Add/update tests.
7. Run lint.
8. Run type checks.
9. Run tests.
10. Show changed files.
11. Explain compatibility impact.
12. Do not perform unrelated refactoring.
```

---

## 61. Initial Development Milestones

### Milestone 1 — Core

```text
[ ] repository scaffold
[ ] CLI
[ ] manifest schema
[ ] models
[ ] loader
[ ] validation
[ ] diagnostics
[ ] adapter interface
[ ] adapter registry
```

### Milestone 2 — Skills + MCP

```text
[ ] skill discovery
[ ] canonical MCP schema
[ ] MCP validation
[ ] normalized internal model
[ ] inspect command
```

### Milestone 3 — First Adapter

```text
[ ] research official spec
[ ] target documentation
[ ] adapter
[ ] golden fixture
[ ] integration test
[ ] generated install README
```

### Milestone 4 — Multi-Target

```text
[ ] second adapter
[ ] third adapter
[ ] capability matrix
[ ] compatibility warnings
[ ] strict mode
```

### Milestone 5 — Distribution

```text
[ ] package archives
[ ] checksums
[ ] release workflow
[ ] standalone executables
```

---

## 62. MVP Acceptance Criteria

MVP is considered usable when the following works:

```bash
git clone <agentpack>
cd agentpack
pip install -e .

agentpack init demo
cd demo

# add one Skill
# add one MCP server

agentpack validate
agentpack inspect
agentpack build
```

And produces at least two genuine client-specific portable artifacts from the same canonical source.

Tests must prove that:

```text
same source
   ↓
different adapters
   ↓
valid target-specific structures
```

without manually duplicating the Skill or MCP definition.

---

## 63. First AI Coding Prompt

Use this as the first implementation prompt after creating the repository:

> Read `AGENTPACK_BASELINE.md` completely and treat it as the architectural source of truth. Scaffold the AgentPack Python project for MVP Milestone 1 only. Implement the CLI skeleton, Pydantic models for the package manifest, manifest loading, basic diagnostics, a target adapter protocol/base class, an adapter registry, and unit tests. Do not implement any real Claude/Copilot/Codex adapters yet. Keep target-specific logic out of the core. Use `pyproject.toml`, Python 3.11+, Typer, Pydantic, pytest, and Ruff. After implementation, run the test suite and linting and summarize the resulting repository structure and any architecture decisions.

---

## 64. Second AI Coding Prompt

After Milestone 1:

> Implement MVP Milestone 2 from `AGENTPACK_BASELINE.md`. Add local Agent Skill discovery, the canonical MCPServer model/schema, semantic validation, and `agentpack inspect`. Do not implement target-specific output yet. Add fixtures for a minimal package, Skills-only package, MCP-only package, and combined package. Ensure secrets are represented symbolically and are never resolved from the local environment during loading or inspection.

---

## 65. First Adapter Prompt Template

Use this template for each target:

> Implement the `<TARGET>` adapter for AgentPack. First read `AGENTPACK_BASELINE.md`. Before changing code, research the current official `<TARGET>` documentation for plugin/extension packaging, Agent Skills support, MCP support, required manifests, installation/import flow, and supported client versions. Record the verified findings in `docs/targets/<target>.md`, including links to official specifications and the verification date. Then implement the adapter through the existing adapter interface. Do not add `<TARGET>` conditionals to generic core code. Add golden fixtures and integration tests. If `<TARGET>` cannot produce a genuine portable artifact that the user can install/import using the target's supported mechanism, classify it as `configuration-export-only` rather than pretending it is a full plugin target.

---

## 66. Architectural Decision Records

Create:

```text
docs/adr/
```

Recommended early ADRs:

```text
0001-canonical-source-model.md
0002-adapter-architecture.md
0003-no-direct-client-installation.md
0004-secrets-are-symbolic.md
0005-deterministic-builds.md
```

ADRs are important because AI coding agents may otherwise gradually drift from the original design.

---

## 67. Important Open Questions

These should be resolved through implementation research rather than assumptions:

```text
[ ] Which current AI clients support true portable plugin packages?
[ ] Which support only configuration import?
[ ] Which support Skills natively?
[ ] Which support packaged MCP definitions?
[ ] Which support user-configurable MCP secrets through UI?
[ ] What universal/open Agent Plugin specification should be treated as canonical?
[ ] Should AgentPack generate archives itself or leave compression to target adapters?
[ ] How should package signing work?
[ ] How should client-version compatibility be represented?
[ ] Should target schemas be vendored or downloaded?
[ ] How should schema updates be tracked?
[ ] What should constitute a backwards-incompatible AgentPack manifest change?
```

---

## 68. Long-Term Direction

The long-term architecture should allow:

```text
                         AgentPack
                            │
               canonical capability model
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
     build                inspect               diff
       │                    │                    │
       ▼                    ▼                    ▼
 target adapters      normalized view      compatibility
       │
       ├── Claude
       ├── Copilot
       ├── Codex
       ├── Cursor
       ├── Gemini
       ├── Universal
       └── third-party adapters
```

Eventually:

```text
Source Repository
      ↓
AgentPack CI
      ↓
Multi-client release artifacts
      ↓
GitHub Release / Registry / Marketplace
      ↓
User installs using native AI-client UI
```

That is the intended end state.

---

## 69. Product Identity

AgentPack should remain focused on one problem:

> **Portable packaging and distribution of reusable AI-agent capabilities across heterogeneous AI clients.**

It succeeds when a developer maintains **one capability source** and users receive **native or supported installable artifacts** for the AI clients they use.

---

## 70. Baseline Status

This document is the initial architectural baseline.

Before implementing any target adapter, verify that target's current official packaging and import mechanisms.

Where this baseline conflicts with a verified target specification:

1. preserve the general AgentPack architecture
2. document the incompatibility
3. implement the target through its adapter
4. update this baseline only if the change is generally applicable
5. create an ADR for significant architectural changes

---

**Tagline candidate**

> **AgentPack — Define once. Package for every AI client.**
