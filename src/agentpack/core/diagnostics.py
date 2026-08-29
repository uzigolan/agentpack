"""Stable diagnostic codes and collection.

Codes are part of the public contract: docs, CI and coding agents key off them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# --- 1xxx: source / schema -------------------------------------------------
AP1001 = "AP1001"  # Invalid manifest
AP1002 = "AP1002"  # Missing skill
AP1003 = "AP1003"  # Invalid MCP definition
AP1004 = "AP1004"  # Duplicate capability name
AP1005 = "AP1005"  # Invalid skill frontmatter
AP1006 = "AP1006"  # Unsafe path (traversal / symlink / outside project)
AP1007 = "AP1007"  # Invalid include

# --- 2xxx: target compatibility -------------------------------------------
AP2001 = "AP2001"  # Unsupported target
AP2101 = "AP2101"  # Unsupported skill feature
AP2201 = "AP2201"  # Unsupported MCP transport
AP2301 = "AP2301"  # Unsupported hook
AP2401 = "AP2401"  # Capability dropped for target
AP2501 = "AP2501"  # Secret must be supplied by the user after install

# --- 3xxx: build -----------------------------------------------------------
AP3001 = "AP3001"  # Build failed
AP3002 = "AP3002"  # Output validation failed


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    target: str | None = None
    source: str | None = None

    def render(self) -> str:
        scope = f" [{self.target}]" if self.target else ""
        where = f" ({self.source})" if self.source else ""
        return f"{self.severity.value} {self.code}{scope}: {self.message}{where}"


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def add(
        self,
        code: str,
        severity: Severity,
        message: str,
        *,
        target: str | None = None,
        source: str | None = None,
    ) -> None:
        self.items.append(Diagnostic(code, severity, message, target, source))

    def error(self, code: str, message: str, **kw: str | None) -> None:
        self.add(code, Severity.ERROR, message, **kw)  # type: ignore[arg-type]

    def warning(self, code: str, message: str, **kw: str | None) -> None:
        self.add(code, Severity.WARNING, message, **kw)  # type: ignore[arg-type]

    def info(self, code: str, message: str, **kw: str | None) -> None:
        self.add(code, Severity.INFO, message, **kw)  # type: ignore[arg-type]

    def extend(self, other: Diagnostics | list[Diagnostic]) -> None:
        self.items.extend(other.items if isinstance(other, Diagnostics) else other)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.WARNING]

    def has_errors(self) -> bool:
        return bool(self.errors)

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class AgentPackError(Exception):
    """Fatal error carrying a diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
