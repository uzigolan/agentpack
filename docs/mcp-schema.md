# Canonical MCP server definition

AgentPack keeps its own normalized MCP representation so adapters never have to
guess. One file per server under `mcp/`.

**Contents:** [stdio](#stdio-server) · [http](#http-server) ·
[Environment](#environment-and-headers) · [Managing definitions](#managing-definitions) ·
[Importing JSON](#importing-from-client-json) · [Mapping](#how-adapters-map-it)

## stdio server

```yaml
apiVersion: agentpack.dev/v1alpha1
kind: MCPServer

metadata:
  name: netops
  displayName: NetOps device access
  description: Read-only device inventory and health tools.

transport:
  type: stdio

command:
  executable: python
  args: ["-m", "netops_mcp.server"]
  cwd: null

environment:
  NETOPS_INVENTORY:
    source: user
    type: file          # string | file | directory | number | boolean
    required: true
    secret: false
    title: Inventory file
    description: Path to inventory.yaml (device facts only, never credentials).
  NETOPS_TOKEN:
    source: user
    required: true
    secret: true
    description: API token for the device gateway.
  NETOPS_READONLY:
    source: literal
    value: "true"

capabilities:
  tools: true
  resources: true
  prompts: false
```

Shorthand: a plain string value is treated as `source: literal`.

```yaml
environment:
  NETOPS_READONLY: "true"
```

## http server

```yaml
transport:
  type: http            # http | sse

endpoint:
  url: https://mcp.example.com/mcp

headers:
  Authorization:
    source: user
    required: true
    secret: true
    description: Bearer token for the monitoring MCP endpoint.
```

## Environment and headers

| Key | Meaning |
|---|---|
| `source: user` | The installing user supplies it. Never baked in. |
| `source: literal` | Non-secret constant, written into the generated config. |
| `secret: true` | Loading fails (`AP1003`) if a `value` is also present. |
| `type` | Hint used by targets that can render a typed picker (MCPB `user_config`). |
| `default` | Only emitted for non-secret values. |

## Managing definitions

Write these files by hand, or let AgentPack maintain them. Edits are
round-tripped, so comments and formatting are preserved.

```powershell
agentpack mcp add netops --command python --arg -m --arg netops_mcp.server ‹
                        --secret NETOPS_TOKEN --env NETOPS_READONLY=true
agentpack mcp add monitoring -t http -u https://mcp.example.com/mcp --header Authorization
agentpack mcp update netops -d "Read-only device access" --remove-env NETOPS_READONLY
agentpack mcp remove monitoring --keep-file
```

| Option | Meaning |
|---|---|
| `-t, --transport` | `stdio` (default), `http` or `sse` |
| `-c, --command` | stdio executable |
| `-a, --arg` | stdio argument; repeatable and ordered |
| `--cwd` | stdio working directory |
| `-u, --url` | endpoint for `http`/`sse` |
| `-e, --env` | `KEY` for a user-supplied value, `KEY=VALUE` for a literal |
| `-s, --secret` | `KEY` of a user-supplied secret |
| `--header` | secret HTTP header name |
| `--remove-env` | drop an environment key (`update` only) |

`mcp add` writes `mcp/<name>.yaml` and registers the directory in the manifest
once. `mcp update` only touches the options you pass.

## Importing from client JSON

If a server is already configured in a client, import it instead of retyping:

```powershell
agentpack mcp import "$env:APPDATA\Code\User\mcp.json"
agentpack mcp import claude_desktop_config.json
agentpack mcp import manifest.json                # an MCPB bundle
agentpack mcp import mcp.json --name netops       # only one server
agentpack mcp import mcp.json --update            # merge into an existing definition
```

Recognised shapes:

| JSON | Source |
|---|---|
| `{"mcpServers": {…}}` | Claude Desktop, Claude Code, most CLIs |
| `{"servers": {…}, "inputs": […]}` | VS Code and JetBrains Copilot |
| `{"manifest_version": …, "server": {…}}` | an MCPB bundle manifest |
| `{"command": …}` or `{"url": …}` | a bare server object; needs `--name` |

Values are classified, never copied blindly:

- `${input:x}`, `${user_config.x}` and `<KEY>` become `source: user`. The
  client's own metadata supplies the description, the type, and whether it is a
  password.
- A key that looks like a credential (`token`, `secret`, `key`, `password`,
  `auth`, …) becomes `source: user, secret: true` **and the value is dropped**,
  even if the JSON contained a real one.
- Everything else becomes `source: literal`.

With `--update`, an incoming `stdio` definition removes a stale `endpoint`, and
an incoming `http` definition removes a stale `command`. Existing declarations
the JSON does not mention are left alone.

## How adapters map it
| Target | stdio | http | user value |
|---|---|---|---|
| `claude-desktop` | `server.mcp_config.command/args/env` | `npx -y mcp-remote <url>` + `--header` | `user_config` prompt, `${user_config.key}` |
| `claude-code` | `mcpServers.<n>` | `mcpServers.<n>.url` | `<KEY>` placeholder |
| `copilot-vscode` | `servers.<n>` | `servers.<n>` type `http` | `inputs[]` + `${input:id}` |
| `copilot-intellij` | same as VS Code | same | same |
| `codex` | `[mcp_servers.<n>]` type `local` | `url` (experimental client) | `<KEY>` placeholder / `bearer_token_env_var` |
| `universal` | verbatim copy | verbatim copy | listed in `plugin.json` |
