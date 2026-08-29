"""Semantic and target-compatibility validation.

Layers: schema (loader/pydantic) -> source -> semantic -> target -> output.
"""

from __future__ import annotations

from collections import Counter

from agentpack.core.diagnostics import (
    AP1002,
    AP1003,
    AP1004,
    AP2001,
    AP2101,
    AP2201,
    AP2301,
    AP2501,
    Diagnostics,
)
from agentpack.core.registry import registry
from agentpack.models.package import AgentPackage, Support, TransportType


def validate_semantics(pkg: AgentPackage, diags: Diagnostics) -> None:
    for label, names in (
        ("skill", [s.name for s in pkg.skills]),
        ("mcp server", [s.name for s in pkg.mcp_servers]),
    ):
        for name, count in Counter(names).items():
            if count > 1:
                diags.error(AP1004, f"duplicate {label} name '{name}' ({count} definitions)")

    if not pkg.skills and not pkg.mcp_servers:
        diags.warning(AP1002, "package declares no skills and no MCP servers")

    for server in pkg.mcp_servers:
        if server.transport is TransportType.STDIO and not server.command:
            diags.error(AP1003, f"mcp server '{server.name}' has no command", source=server.name)


def validate_targets(pkg: AgentPackage, targets: list[str], diags: Diagnostics) -> None:
    for name in targets:
        adapter = registry.get(name)
        if adapter is None:
            diags.error(
                AP2001,
                f"unknown target '{name}'. Known: {', '.join(registry.names())}",
                target=name,
            )
            continue

        caps = adapter.capabilities()
        policy = pkg.compatibility_policy.value
        report = diags.error if policy == "error" else diags.warning
        if policy == "ignore":
            report = diags.info

        if pkg.skills and caps.skills is Support.NONE:
            report(AP2101, f"{len(pkg.skills)} skill(s) cannot be represented", target=name)
        for server in pkg.mcp_servers:
            supported = caps.mcp_http if server.is_remote else caps.mcp_stdio
            if supported is Support.NONE:
                report(
                    AP2201,
                    f"transport '{server.transport.value}' is unsupported "
                    f"(server '{server.name}')",
                    target=name,
                )
        if pkg.hooks and caps.hooks is Support.NONE:
            report(AP2301, f"{len(pkg.hooks)} hook(s) were omitted", target=name)

        if caps.user_config is Support.NONE:
            required = [
                f"{s.name}.{k}"
                for s in pkg.mcp_servers
                for k, v in s.user_inputs().items()
                if v.required
            ]
            if required:
                diags.info(
                    AP2501,
                    "target cannot prompt for values; install docs will list "
                    + ", ".join(required),
                    target=name,
                )

        diags.extend(adapter.validate(pkg))


def validate(pkg: AgentPackage, targets: list[str] | None = None) -> Diagnostics:
    diags = Diagnostics()
    validate_semantics(pkg, diags)
    validate_targets(pkg, targets or pkg.targets, diags)
    return diags
