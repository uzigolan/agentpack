# Canonical MCP server definition

AgentPack keeps its own normalized MCP representation so adapters never have to
guess. One file per server under `mcp/`.

**Contents:** [stdio](#stdio-server) · [http](#http-server) ·
[Environment](#environment-and-headers) · [Mapping](#how-adapters-map-it)

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

## How adapters map it

| Target | stdio | http | user value |
|---|---|---|---|
| `claude-desktop` | `server.mcp_config.command/args/env` | `npx -y mcp-remote <url>` + `--header` | `user_config` prompt, `${user_config.key}` |
| `claude-code` | `mcpServers.<n>` | `mcpServers.<n>.url` | `<KEY>` placeholder |
| `copilot-vscode` | `servers.<n>` | `servers.<n>` type `http` | `inputs[]` + `${input:id}` |
| `copilot-intellij` | same as VS Code | same | same |
| `codex` | `[mcp_servers.<n>]` type `local` | `url` (experimental client) | `<KEY>` placeholder / `bearer_token_env_var` |
| `universal` | verbatim copy | verbatim copy | listed in `plugin.json` |
