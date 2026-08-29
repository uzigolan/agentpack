# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The canonical manifest schema (`apiVersion`) is versioned independently of the
CLI; see [docs/manifest.md](docs/manifest.md).

## [Unreleased]

### Added

- `agentpack skill add|remove` and `agentpack mcp add|update|remove` to maintain
  an existing manifest. `skill add` is idempotent and recognises a covering
  parent entry. Edits are round-tripped, so comments and formatting survive.
- `agentpack mcp import FILE.json` to create or (`--update`) merge MCP
  definitions from a client's JSON config: `mcpServers`, `servers` with
  `inputs`, an MCPB `manifest.json`, or a bare server object. Placeholders and
  credential-looking keys become user-supplied declarations; no value is copied.
- `agentpack init` now takes `--name/-n`, `--file/-f` for the manifest filename,
  and `--bare` for a manifest with no example skill or MCP server.
- `INSTALL.md` at the repo root: pipx / virtualenv / from-source installation,
  verification, upgrade, uninstall and troubleshooting.
- `dist/INSTALL.md`, generated on every build: an index of every artifact, which
  client it belongs to, per-client install steps and the required-value table.
- `TargetAdapter.install_steps()` and `required_values_table()` are now public,
  so adapters contribute to both the per-target README and the install guide.
- `-f` / `--file` on `validate`, `build`, `package`, `inspect`, `clean` and
  `doctor` to use a specific manifest with any filename. Paths inside it resolve
  relative to the manifest's directory.
- `package` now accepts `--strict` and `--knowledge`, matching `build`.

### Changed

- `inspect --format` lost its `-f` short alias, which now means `--file`.
- Manifest load errors exit cleanly with the diagnostic code instead of a
  traceback, whichever entry point is used.

## [0.1.0] - 2026-08-29

First working release.

### Added

- Canonical project format: `agentpack.yaml`, directory-based skills with a
  `SKILL.md` frontmatter contract, and normalized MCP server definitions
  (`stdio`, `http`, `sse`).
- CLI: `init`, `validate`, `inspect`, `build`, `package`, `list-targets`,
  `clean`, `doctor`, `version`.
- Target adapters: `claude-desktop` (MCPB bundles + skills plugin),
  `claude-code` (plugin + marketplace), `copilot-vscode`, `copilot-intellij`,
  `codex` (TOML), `universal` (loss-free archive).
- `include:` composition so each producing repository keeps its own
  `agentpack.yaml` as the single definition of what it ships.
- Knowledge modes `bundled` / `served`, with a `<!--agentpack-mode:served-->`
  stamp for runtime detection.
- Secret declarations mapped to each client's native mechanism: MCPB
  `user_config`, VS Code `inputs`/`${input:}`, Codex `bearer_token_env_var`, or
  documented `<KEY>` placeholders. Secret values are never embedded.
- HTTP MCP servers reach Claude Desktop through an `npx -y mcp-remote` bridge.
- Deterministic builds: sorted entries, fixed archive timestamps, and a SHA-256
  per target recorded in `dist/agentpack-build.json`.
- Stable diagnostic codes (`AP1001`–`AP3002`) with `--strict` mode.
- Generated per-target install README with required-value tables.
- Adapter registry with an `agentpack.targets` entry-point group for
  third-party adapters.

[Unreleased]: https://github.com/uzigolan/agentpack/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/uzigolan/agentpack/releases/tag/v0.1.0
