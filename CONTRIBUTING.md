# Contributing

**Contents:** [Setup](#setup) · [Checks](#checks) · [Adding an adapter](#adding-an-adapter) ·
[Rules](#project-rules) · [Commits and PRs](#commits-and-prs)

## Setup

From the repo root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Checks

Run both before opening a pull request:

```powershell
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m pytest -q
```

And confirm the example still builds for every target:

```powershell
cd examples\network-operations
..\..\.venv\Scripts\agentpack.exe validate
..\..\.venv\Scripts\agentpack.exe package
```

CI runs the same commands plus a reproducibility check: building twice must
produce identical per-target SHA-256 values in `dist/agentpack-build.json`.

## Adding an adapter

1. Answer the research checklist in [docs/compatibility.md](docs/compatibility.md)
   against the client's **current official documentation**. Do not implement
   from assumptions.
2. Add `src/agentpack/adapters/<client>.py` with a `TargetAdapter` subclass.
3. Register it in `_BUILTINS` in [src/agentpack/core/registry.py](src/agentpack/core/registry.py).
4. Add a section to [docs/adapters.md](docs/adapters.md) recording the file
   format, config paths per OS, and the import mechanism.
5. Add tests that pin the generated shape — the exact config keys matter more
   than anything else in this project.

Third-party adapters do not need to live here; register through the
`agentpack.targets` entry-point group instead.

## Project rules

These are not style preferences; breaking them breaks the product.

1. **Never write into a client's configuration directory.** AgentPack writes
   into `dist/` only. Installation happens through the client's own UI or import
   command.
2. **Never install skills one by one.** Skills travel inside the target's
   package so it installs and uninstalls as one unit.
3. **Never embed a secret.** Values declared `secret: true` become a client
   prompt or a documented placeholder. The local environment is never read.
4. **Never execute anything during a build.** No skill scripts, no MCP commands,
   no hooks. Source repositories are untrusted input.
5. **Keep target logic in adapters.** No `if target == ...` in core.
6. **Keep builds deterministic.** Sorted entries, fixed archive timestamps.
7. **Name every artifact for its target**:
   `<package>-<target>[-<part>]-<version><suffix>`.
8. **Diagnostic codes are a public contract.** Add new codes; do not repurpose
   existing ones.

## Commits and PRs

- One logical change per pull request.
- Update [CHANGELOG.md](CHANGELOG.md) under `Unreleased`.
- If you change generated output, say which client and which version you
  verified against.
