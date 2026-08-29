"""Edit an existing manifest and MCP definitions in place.

Round-trip YAML is used so a hand-written manifest keeps its comments, key order
and formatting. Only the entries being changed are touched.
"""

from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
from typing import Any

from ruamel.yaml import YAML

from agentpack import API_VERSION
from agentpack.core.diagnostics import AP1001, AP1003, AgentPackError

DEFAULT_MCP_DIR = "mcp"
DEFAULT_SKILLS_DIR = "skills"


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 100
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def read_doc(path: Path) -> Any:
    if not path.is_file():
        raise AgentPackError(AP1001, f"not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return _yaml().load(fh) or {}


def write_doc(path: Path, doc: Any) -> None:
    buf = io.StringIO()
    _yaml().dump(doc, buf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")


def normalize(value: str) -> str:
    """Comparable form of a path entry: posix, no leading ./, no trailing /."""
    text = str(value).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/") or "."


def entry_path(entry: Any) -> str:
    return normalize(entry.get("path", "") if isinstance(entry, dict) else entry)


def find_entry(doc: Any, key: str, value: str) -> int | None:
    target = normalize(value)
    for index, entry in enumerate(doc.get(key) or []):
        if entry_path(entry) == target:
            return index
    return None


def add_entry(doc: Any, key: str, value: str) -> bool:
    """Register a path under ``key``. Returns False if it was already there."""
    if find_entry(doc, key, value) is not None:
        return False
    if not doc.get(key):
        doc[key] = []
    doc[key].append({"path": normalize(value)})
    return True


def remove_entry(doc: Any, key: str, value: str) -> bool:
    index = find_entry(doc, key, value)
    if index is None:
        return False
    del doc[key][index]
    return True


def covering_entry(doc: Any, key: str, value: str) -> str | None:
    """An existing entry that is ``value`` itself or a parent directory of it."""
    target = PurePosixPath(normalize(value))
    for entry in doc.get(key) or []:
        existing = PurePosixPath(entry_path(entry))
        if target == existing or existing in target.parents:
            return str(existing)
    return None


def default_dir(doc: Any, key: str, fallback: str) -> str:
    """Where new files of this kind should live, inferred from the manifest."""
    for entry in doc.get(key) or []:
        path = entry_path(entry)
        if not path.endswith((".yaml", ".yml")):
            return path
    return fallback


# --------------------------------------------------------------------------
# MCP definitions
# --------------------------------------------------------------------------
def mcp_document(
    name: str,
    *,
    transport: str = "stdio",
    description: str = "",
    display_name: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    cwd: str | None = None,
    url: str | None = None,
    env: list[str] | None = None,
    secret_env: list[str] | None = None,
    headers: list[str] | None = None,
) -> dict:
    metadata: dict[str, Any] = {"name": name}
    if display_name:
        metadata["displayName"] = display_name
    if description:
        metadata["description"] = description

    doc: dict[str, Any] = {
        "apiVersion": API_VERSION,
        "kind": "MCPServer",
        "metadata": metadata,
        "transport": {"type": transport},
    }

    if transport == "stdio":
        if not command:
            raise AgentPackError(AP1003, "stdio transport needs --command")
        doc["command"] = {"executable": command, "args": list(args or [])}
        if cwd:
            doc["command"]["cwd"] = cwd
    else:
        if not url:
            raise AgentPackError(AP1003, f"{transport} transport needs --url")
        doc["endpoint"] = {"url": url}

    environment: dict[str, Any] = {}
    for key in env or []:
        name_, _, value = key.partition("=")
        environment[name_] = (
            {"source": "literal", "value": value}
            if value
            else {"source": "user", "required": True, "secret": False, "description": ""}
        )
    for key in secret_env or []:
        environment[key] = {
            "source": "user",
            "required": True,
            "secret": True,
            "description": f"Secret value for {key}.",
        }
    if environment:
        doc["environment"] = environment

    if headers:
        doc["headers"] = {
            key: {
                "source": "user",
                "required": True,
                "secret": True,
                "description": f"Secret value for the {key} header.",
            }
            for key in headers
        }

    doc["capabilities"] = {"tools": True}
    return doc


def apply_mcp_updates(doc: Any, **changes: Any) -> list[str]:
    """Overwrite only the fields that were supplied. Returns what changed."""
    changed: list[str] = []

    if changes.get("description"):
        doc.setdefault("metadata", {})["description"] = changes["description"]
        changed.append("description")
    if changes.get("display_name"):
        doc.setdefault("metadata", {})["displayName"] = changes["display_name"]
        changed.append("displayName")

    transport = changes.get("transport")
    if transport:
        doc["transport"] = {"type": transport}
        changed.append("transport")
        if transport == "stdio":
            doc.pop("endpoint", None)
            doc.pop("headers", None)
        else:
            doc.pop("command", None)

    if changes.get("command"):
        doc["command"] = {"executable": changes["command"], "args": list(changes.get("args") or [])}
        changed.append("command")
    elif changes.get("args"):
        doc.setdefault("command", {})["args"] = list(changes["args"])
        changed.append("args")
    if changes.get("cwd"):
        doc.setdefault("command", {})["cwd"] = changes["cwd"]
        changed.append("cwd")

    if changes.get("url"):
        doc["endpoint"] = {"url": changes["url"]}
        changed.append("url")

    for key in changes.get("env") or []:
        name_, _, value = key.partition("=")
        doc.setdefault("environment", {})[name_] = (
            {"source": "literal", "value": value}
            if value
            else {"source": "user", "required": True, "secret": False, "description": ""}
        )
        changed.append(f"env {name_}")
    for key in changes.get("secret_env") or []:
        doc.setdefault("environment", {})[key] = {
            "source": "user",
            "required": True,
            "secret": True,
            "description": f"Secret value for {key}.",
        }
        changed.append(f"env {key}")
    for key in changes.get("remove_env") or []:
        if doc.get("environment", {}).pop(key, None) is not None:
            changed.append(f"removed env {key}")
    for key in changes.get("headers") or []:
        doc.setdefault("headers", {})[key] = {
            "source": "user",
            "required": True,
            "secret": True,
            "description": f"Secret value for the {key} header.",
        }
        changed.append(f"header {key}")

    return changed
