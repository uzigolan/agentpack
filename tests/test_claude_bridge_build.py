from __future__ import annotations

from pathlib import Path

import pytest

from agentpack.adapters import claude_desktop


def test_windows_bridge_falls_back_to_python_without_go(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, str]] = []

    def build_python(output: Path, revision: str) -> None:
        calls.append((output, revision))
        output.write_bytes(b"python-bridge")

    monkeypatch.setattr(claude_desktop.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(claude_desktop.shutil, "which", lambda command: None)
    monkeypatch.setattr(claude_desktop, "_build_python_bridge", build_python)

    output = claude_desktop._windows_bridge()

    assert output.read_bytes() == b"python-bridge"
    assert calls == [(output, output.parent.name)]


def test_windows_bridge_prefers_go(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, str]] = []

    def build_go(output: Path, revision: str) -> None:
        calls.append((output, revision))
        output.write_bytes(b"go-bridge")

    monkeypatch.setattr(claude_desktop.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(claude_desktop.shutil, "which", lambda command: "go.exe")
    monkeypatch.setattr(claude_desktop, "_build_go_bridge", build_go)

    output = claude_desktop._windows_bridge()

    assert output.read_bytes() == b"go-bridge"
    assert calls == [(output, output.parent.name)]


def test_python_bridge_reports_missing_build_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(claude_desktop.importlib.util, "find_spec", lambda package: None)

    with pytest.raises(RuntimeError, match=r"mcp, PyInstaller.*bridge-python"):
        claude_desktop._build_python_bridge(tmp_path / "bridge.exe", "revision")


def test_python_bridge_parses_repeated_headers() -> None:
    pytest.importorskip("mcp")
    from agentpack.bridge.http_bridge import _headers

    assert _headers(
        ["Authorization: Bearer token", "X-RAD-Market-Token: market-token"]
    ) == {
        "Authorization": "Bearer token",
        "X-RAD-Market-Token": "market-token",
    }


def test_python_bridge_rejects_invalid_header() -> None:
    pytest.importorskip("mcp")
    from agentpack.bridge.http_bridge import _headers

    with pytest.raises(ValueError, match="invalid --header"):
        _headers(["missing-separator"])
