"""Windows stdio-to-HTTP MCP bridge, frozen into an executable by PyInstaller."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import multiprocessing
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

BRIDGE_EXECUTABLE = "agentpack-http-bridge.exe"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentPack stdio-to-HTTP MCP bridge")
    parser.add_argument("--url", required=True, help="HTTP MCP endpoint")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="HTTP header, for example 'Authorization: Bearer token'",
    )
    parser.add_argument("--installed", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def _headers(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, header_value = value.partition(":")
        if not separator or not key.strip():
            raise ValueError("invalid --header")
        result[key.strip()] = header_value.strip()
    return result


def _frozen_executable() -> Path:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("the Python HTTP bridge must run as a frozen executable")
    return Path(sys.executable).resolve()


def _installed_executable(source: Path) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return Path(local_app_data) / "AgentPack" / "bridge" / digest / BRIDGE_EXECUTABLE


def _install_and_restart() -> int:
    source = _frozen_executable()
    target = _installed_executable(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target and not target.exists():
        temporary = target.with_name(f"{target.name}.{os.getpid()}.new")
        try:
            shutil.copyfile(source, temporary)
            try:
                temporary.replace(target)
            except OSError:
                # Another Claude session may have installed the same immutable
                # executable while this process was copying it.
                if not target.exists():
                    raise
        finally:
            temporary.unlink(missing_ok=True)
    completed = subprocess.run([str(target), *sys.argv[1:], "--installed"], check=False)
    return completed.returncode


async def _proxy(endpoint: str, headers: dict[str, str]) -> None:
    http_headers = dict(headers)
    # Go's HTTP server rejects state-changing requests without same-origin
    # evidence. Supplying Origin is safe here because this is not a browser.
    parsed = httpx.URL(endpoint)
    http_headers.setdefault("Origin", f"{parsed.scheme}://{parsed.netloc.decode()}")

    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(
        headers=http_headers, timeout=timeout, follow_redirects=True
    ) as client:
        async with streamable_http_client(endpoint, http_client=client) as (
            remote_read,
            remote_write,
            _,
        ):
            async with ClientSession(remote_read, remote_write) as session:
                await session.initialize()
                listed = await session.list_tools()
                server = Server("agentpack-http-proxy")

                @server.list_tools()
                async def list_tools() -> list[types.Tool]:
                    return listed.tools

                @server.call_tool()
                async def call_tool(
                    name: str, arguments: dict[str, object]
                ) -> types.CallToolResult:
                    return await session.call_tool(name, arguments)

                async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                    await server.run(
                        read_stream,
                        write_stream,
                        InitializationOptions(
                            server_name="agentpack-http-proxy",
                            server_version="python",
                            capabilities=server.get_capabilities(
                                notification_options=NotificationOptions(),
                                experimental_capabilities={},
                            ),
                        ),
                    )


def main() -> None:
    multiprocessing.freeze_support()
    args = _arguments()
    if not args.installed:
        try:
            raise SystemExit(_install_and_restart())
        except Exception as exc:
            print(f"AgentPack bridge install: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    try:
        headers = _headers(args.header)
        asyncio.run(_proxy(args.url, headers))
    except Exception as exc:
        print(f"HTTP MCP connection: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
