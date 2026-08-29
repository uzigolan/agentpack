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
  output: dist
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

GITIGNORE = """dist/
.env
"""

README = """# {title}

Built with [AgentPack](https://github.com/) - author once, package for many AI clients.

**Contents:** [Layout](#layout) · [Build](#build) · [Install](#install)

## Layout

```text
agentpack.yaml   canonical manifest
skills/          agent skills (SKILL.md per directory)
mcp/             canonical MCP server definitions
```

## Build

```bash
agentpack validate
agentpack build
agentpack package        # distributable archives
```

## Install

Each directory under `dist/build/<target>/` contains a README with the exact
install steps for that client.
"""


def init_project(directory: Path, name: str) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").replace("_", " ").title()
    files = {
        "agentpack.yaml": MANIFEST.format(api=API_VERSION, name=name, title=title),
        "skills/example/SKILL.md": SKILL,
        "mcp/example.yaml": MCP.format(api=API_VERSION),
        ".gitignore": GITIGNORE,
        "README.md": README.format(title=title),
    }
    written: list[str] = []
    for rel, content in files.items():
        path = directory / rel
        if path.exists():
            continue
        write_text(path, content)
        written.append(rel)
    return written
