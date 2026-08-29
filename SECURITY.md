# Security Policy

**Contents:** [Reporting](#reporting-a-vulnerability) · [Threat model](#threat-model) ·
[Guarantees](#guarantees) · [Out of scope](#out-of-scope)

## Reporting a vulnerability

Please report security issues privately through GitHub's
**Security → Report a vulnerability** advisory form rather than a public issue.

Include: affected version, a reproduction (ideally a minimal `agentpack.yaml`),
and the impact you observed. Please do not include real secrets in a report.

## Threat model

AgentPack reads a project directory that it treats as **untrusted input** and
writes package artifacts. The interesting attacks are therefore:

- a malicious manifest reading or packaging files outside the project;
- a malicious skill or MCP definition causing code execution during a build;
- a crafted archive path escaping extraction on the installing machine;
- a secret leaking into a distributed artifact or into build logs.

## Guarantees

The build enforces all of these, with tests:

- **No execution.** Skill scripts, MCP commands and hooks are never run during
  `validate`, `inspect`, `build` or `package`.
- **No path escape.** Source paths are resolved and checked to stay inside the
  project root (`AP1006`); symlinks are refused rather than followed.
- **Bounded output.** Files are only written inside the configured output
  directory.
- **No secret material.** Values declared `secret: true` are rejected at load
  time if they carry a value; the local environment is never read for secrets;
  generated artifacts contain prompts or placeholders only.
- **Deterministic artifacts.** Identical input produces identical output, and
  `dist/agentpack-build.json` records a SHA-256 per target so a consumer can
  verify what they received.

`include:` may reference a sibling checkout outside the project root. That is
reported as a diagnostic, and each included project's own file access remains
confined to its own root.

## Out of scope

- Vulnerabilities in the MCP servers or skills you package. AgentPack copies
  your content; it does not audit it.
- Vulnerabilities in the target AI clients or in `mcp-remote`.
- Anything requiring an attacker to already control your machine or your
  build environment.

## Supported versions

Pre-1.0: only the latest release receives fixes.
