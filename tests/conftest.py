from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentpack.core.diagnostics import Diagnostics
from agentpack.core.loader import load_package

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "network-operations"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "network-operations"
    shutil.copytree(EXAMPLE, dest, ignore=shutil.ignore_patterns("dist"))
    return dest


@pytest.fixture()
def package(project: Path):
    return load_package(project, Diagnostics())
