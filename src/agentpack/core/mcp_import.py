"""Convert client-native MCP JSON into the canonical definition.

Recognised shapes:

- ``{"mcpServers": {...}}``   Claude Desktop / Claude Code / most CLIs
- ``{"servers": {...}}``      VS Code and JetBrains Copilot, with ``inputs``
- ``{"manifest_version": ..., "server": {...}}``  an MCPB bundle manifest
- a bare server object, e.g. ``{"command": "npx", "args": [...]}``

A value the user must supply is never turned into a literal: placeholders such
as ``${input:x}``, ``${user_config.x}`` and ``<KEY>`` become
``source: user``, and anything that looks like a credential is marked secret.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentpack import API_VERSION
from agentpack.core.diagnostics import AP1003, AgentPackError

SECRET_HINTS = (
    "token",
    "secret",
    "key",
    "password",
    "passwd",
    "auth",
    "credential",
    "apikey",
    "pat",
)

PLACEHOLDER = re.compile(r"^\$\{(?:input:|user_config\.)[^}]+\}$|^<[^>]+>$")
INPUT_REF = re.compile(r"^\$\{input:([^}]+)\}$")
USER_CONFIG_REF = re.compile(r"^\$\{user_config\.([^}]+)\}$")

_REMOTE_TYPES = {"http", "sse", "streamable-http", "streamableHttp", "remote"}


def looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in SECRET_HINTS)


def _declare(key: str, value: Any, hints: dict[str, dict]) -> dict:
    """One environment or header entry, as a canonical declaration."""
    text = value if isinstance(value, str) else json.dumps(value)

    if PLACEHOLDER.match(text):
        hint: dict[str, Any] = {}
        for pattern in (INPUT_REF, USER_CONFIG_REF):
            match = pattern.match(text)
            if match:
                hint = hints.get(match.group(1), {})
                break
        secret = bool(hint.get("password") or hint.get("sensitive")) or looks_secret(key)
        declaration: dict[str, Any] = {
            "source": "user",
            "required": bool(hint.get("required", True)),
            "secret": secret,
            "description": hint.get("description") or f"Value for {key}.",
        }
        if hint.get("type") in ("file", "directory", "number", "boolean"):
            declaration["type"] = hint["type"]
        if not secret and hint.get("default"):
            declaration["default"] = hint["default"]
        return declaration

    if looks_secret(key):
        # A real credential was sitting in the source file; never carry it over.
        return {
            "source": "user",
            "required": True,
            "secret": True,
            "description": f"Value for {key}.",
        }
    return {"source": "literal", "value": text}


def _server_document(name: str, entry: dict, hints: dict[str, dict]) -> dict:
    declared_type = str(entry.get("type") or "").strip()
    url = entry.get("url") or entry.get("endpoint")

    if url:
        transport = declared_type if declared_type in ("http", "sse") else "http"
    elif entry.get("command"):
        transport = "stdio"
    else:
        raise AgentPackError(AP1003, f"'{name}': JSON has neither 'command' nor 'url'")

    metadata: dict[str, Any] = {"name": name}
    for source_key, target_key in (("displayName", "displayName"), ("description", "description")):
        if entry.get(source_key):
            metadata[target_key] = entry[source_key]

    doc: dict[str, Any] = {
        "apiVersion": API_VERSION,
        "kind": "MCPServer",
        "metadata": metadata,
        "transport": {"type": transport},
    }

    if transport == "stdio":
        doc["command"] = {
            "executable": entry["command"],
            "args": [str(a) for a in entry.get("args") or []],
        }
        if entry.get("cwd"):
            doc["command"]["cwd"] = entry["cwd"]
    else:
        doc["endpoint"] = {"url": url}
        headers = {k: _declare(k, v, hints) for k, v in (entry.get("headers") or {}).items()}
        if entry.get("bearer_token_env_var") and not headers:
            headers["Authorization"] = _declare("Authorization", "<TOKEN>", hints)
        if headers:
            doc["headers"] = headers

    environment = {k: _declare(k, v, hints) for k, v in (entry.get("env") or {}).items()}
    if environment:
        doc["environment"] = environment

    doc["capabilities"] = {"tools": True}
    return doc


def _hints(data: dict) -> dict[str, dict]:
    """Metadata about user-supplied values, keyed by placeholder id."""
    hints: dict[str, dict] = {}
    for item in data.get("inputs") or []:
        if isinstance(item, dict) and item.get("id"):
            hints[item["id"]] = item
    for key, value in (data.get("user_config") or {}).items():
        if isinstance(value, dict):
            hints[key] = value
    return hints


def servers_from_json(data: Any, name: str | None = None) -> list[tuple[str, dict]]:
    """Return ``(name, canonical document)`` for every server in the JSON."""
    if not isinstance(data, dict):
        raise AgentPackError(AP1003, "JSON root must be an object")

    hints = _hints(data)

    if data.get("manifest_version") and isinstance(data.get("server"), dict):
        entry = data["server"].get("mcp_config") or {}
        bundle_name = name or data.get("name") or "imported"
        entry.setdefault("description", data.get("description", ""))
        return [(bundle_name, _server_document(bundle_name, entry, hints))]

    collection = data.get("mcpServers") or data.get("servers") or data.get("mcp_servers")
    if isinstance(collection, dict):
        wanted = [name] if name else sorted(collection)
        missing = [w for w in wanted if w not in collection]
        if missing:
            raise AgentPackError(
                AP1003, f"'{missing[0]}' not in JSON. Found: {', '.join(sorted(collection))}"
            )
        return [(key, _server_document(key, collection[key], hints)) for key in wanted]

    if data.get("command") or data.get("url"):
        if not name:
            raise AgentPackError(AP1003, "a bare server object needs --name")
        return [(name, _server_document(name, data, hints))]

    raise AgentPackError(
        AP1003, "no MCP server found; expected 'mcpServers', 'servers' or a server object"
    )


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise AgentPackError(AP1003, f"not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentPackError(AP1003, f"{path.name} is not valid JSON: {exc}") from exc


def merge_server(existing: Any, incoming: dict) -> list[str]:
    """Apply an imported document onto an existing one. Returns what changed."""
    changed: list[str] = []

    for key in ("displayName", "description"):
        value = incoming.get("metadata", {}).get(key)
        if value and existing.setdefault("metadata", {}).get(key) != value:
            existing["metadata"][key] = value
            changed.append(key)

    transport = incoming.get("transport", {}).get("type")
    if transport and existing.get("transport", {}).get("type") != transport:
        existing["transport"] = {"type": transport}
        changed.append("transport")
    if transport == "stdio":
        existing.pop("endpoint", None)
    elif transport:
        existing.pop("command", None)

    for key in ("command", "endpoint"):
        if key in incoming and existing.get(key) != incoming[key]:
            existing[key] = incoming[key]
            changed.append(key)

    for section in ("environment", "headers"):
        for key, value in (incoming.get(section) or {}).items():
            current = existing.setdefault(section, {})
            if current.get(key) != value:
                current[key] = value
                changed.append(f"{section}.{key}")

    return changed
