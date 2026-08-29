## What changed

<!-- One sentence. -->

## Why

<!-- The problem this solves. Link the issue if there is one. -->

## Checklist

- [ ] `ruff check src tests` passes
- [ ] `pytest -q` passes
- [ ] `examples/network-operations` still validates and packages
- [ ] `CHANGELOG.md` updated under `Unreleased`

## If this touches an adapter

- [ ] Client and version verified against: <!-- e.g. Claude Desktop 1.x, docs link -->
- [ ] `docs/adapters.md` updated (file format, config paths, import mechanism)
- [ ] Tests pin the generated config keys

## Project rules

Confirm none of these were broken (see [CONTRIBUTING.md](../CONTRIBUTING.md)):

- [ ] Nothing is written into a client configuration directory
- [ ] Skills are not installed one by one
- [ ] No secret value can reach a generated artifact
- [ ] Nothing is executed during a build
- [ ] Build output is still deterministic
