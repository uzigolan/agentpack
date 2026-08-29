"""Project scaffolding for ``agentpack init``."""

from __future__ import annotations

from pathlib import Path

from agentpack import API_VERSION
from agentpack.core.fsutil import write_text

MANIFEST = """apiVersion: {api}
kind: AgentPackage

metadata:
  name: {name}
  displayName: {title}
  version: 0.1.0
  description: Describe what this package gives an AI agent.
  license: Apache-2.0
  authors:
    - name: Your Name

targets:
  - universal
  - claude-desktop
  - claude-code
  - copilot-vscode
  - codex

skills:
  - path: skills/

mcp:
  - path: mcp/

prompts: []
assets: []

build:
  output: {output}
  clean: true
  reproducible: true
  knowledge: bundled   # bundled | served

compatibility:
  unsupportedFeaturePolicy: warn   # ignore | warn | error
"""

SKILL = """---
name: example
description: >-
  Example AgentPack skill. Replace this with a precise trigger description -
  clients use it to decide when to load the skill.
version: 0.1.0
---

# Example Skill

Use this skill when the user requests an example operation.

## Steps

1. Confirm what the user is asking for.
2. Do the thing.
3. Report the result.
"""

MCP = """apiVersion: {api}
kind: MCPServer

metadata:
  name: example
  description: Example MCP server.

transport:
  type: stdio

command:
  executable: npx
  args:
    - "-y"
    - "@example/mcp-server"

environment:
  EXAMPLE_TOKEN:
    source: user
    required: true
    secret: true
    description: API token for the example service.

capabilities:
  tools: true
  resources: false
  prompts: false
"""

GITIGNORE = """{output}/
.env
"""

BARE_MANIFEST = """apiVersion: {api}
kind: AgentPackage

metadata:
  name: {name}
  displayName: {title}
  version: 0.1.0
  description: Describe what this package gives an AI agent.

targets:
  - universal
  - claude-desktop
  - claude-code
  - copilot-vscode
  - codex

# Register capabilities with:
#   agentpack skill add skills/my-skill
#   agentpack mcp add my-server --command python --arg -m --arg my_mcp.server
skills: []

mcp: []

build:
  output: {output}     # every generated artifact goes here
  knowledge: bundled   # bundled | served

compatibility:
  unsupportedFeaturePolicy: warn   # ignore | warn | error
"""

README = """# {title}

Built with [AgentPack](https://github.com/uzigolan/agentpack) - author once,
package for many AI clients.

**Contents:** [Layout](#layout) · [Build](#build) · [Install](#install)

## Layout

```text
{manifest}   canonical manifest
skills/          agent skills (SKILL.md per directory)
mcp/             canonical MCP server definitions
{output}/{output_pad}every generated artifact
```

## Build

```bash
agentpack validate{flag}
agentpack build{flag}
agentpack package{flag}        # distributable archives
```

## Install

`{output}/INSTALL.md` lists every artifact that was produced and how to install it.
"""


def init_project(
    directory: Path,
    name: str,
    manifest_name: str = "agentpack.yaml",
    *,
    example: bool = False,
    output: str = "dist",
) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").replace("_", " ").title()
    default_name = manifest_name in ("agentpack.yaml", "agentpack.yml")

    files = {
        manifest_name: (MANIFEST if example else BARE_MANIFEST).format(
            api=API_VERSION, name=name, title=title, output=output
        ),
        ".gitignore": GITIGNORE.format(output=output),
        "README.md": README.format(
            title=title,
            manifest=manifest_name,
            output=output,
            output_pad=" " * max(1, 16 - len(output) - 1),
            flag="" if default_name else f" -f {manifest_name}",
        ),
    }
    if example:
        files["skills/example/SKILL.md"] = SKILL
        files["mcp/example.yaml"] = MCP.format(api=API_VERSION)

    written: list[str] = []
    for rel, content in files.items():
        path = directory / rel
        if path.exists():
            continue
        write_text(path, content)
        written.append(rel)
    return written
