"""Filesystem helpers with path-safety and deterministic archiving.

Security: source repositories are treated as untrusted. Nothing is ever
executed, nothing is written outside the configured output directory, and
symlinks / traversal are rejected.
"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agentpack.core.diagnostics import AP1006, AP3001, AgentPackError

# Fixed timestamp so archives are byte-identical across builds (1980-01-01,
# the earliest value the ZIP format can represent).
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

IGNORED_NAMES = {".git", ".DS_Store", "__pycache__", ".venv", "node_modules"}


def ensure_inside(root: Path, candidate: Path) -> Path:
    """Return the resolved path, or raise if it escapes ``root``."""
    root_r = root.resolve()
    cand_r = candidate.resolve()
    if root_r != cand_r and root_r not in cand_r.parents:
        raise AgentPackError(AP1006, f"path escapes project root: {candidate}")
    return cand_r


def iter_files(base: Path) -> list[Path]:
    """Sorted, relative file list under ``base``; symlinks are rejected."""
    out: list[Path] = []
    for path in sorted(base.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.relative_to(base).parts):
            continue
        if path.is_symlink():
            raise AgentPackError(AP1006, f"symlinks are not packaged: {path}")
        if path.is_file():
            out.append(path.relative_to(base))
    return sorted(out, key=lambda p: str(p).replace("\\", "/"))


def copy_tree(src: Path, dst: Path, *, exclude: Iterable[str] = ()) -> list[str]:
    """Copy ``src`` into ``dst``; returns written paths relative to ``dst``."""
    excluded = tuple(e.rstrip("/") + "/" for e in exclude)
    written: list[str] = []
    for rel in iter_files(src):
        posix = str(rel).replace("\\", "/")
        if posix.startswith(excluded):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, target)
        written.append(posix)
    return written


def write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return path.name


def write_json(path: Path, data: Any) -> str:
    return write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False))


def zip_dir(source: Path, archive: Path, *, arc_root: str | None = None) -> Path:
    """Deterministic zip: sorted entries, fixed timestamps, stored permissions."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in iter_files(source):
            posix = str(rel).replace("\\", "/")
            arcname = f"{arc_root}/{posix}" if arc_root else posix
            info = zipfile.ZipInfo(arcname, date_time=ZIP_EPOCH)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (source / rel).read_bytes())
    return archive


def remove_tree(path: Path) -> None:
    """Remove a generated directory, tolerating brief Windows file locks.

    Antivirus and Explorer can hold a native DLL/PYD in a just-written package
    for a moment. Retry those transient locks; otherwise raise a concise
    AgentPack error instead of leaking a Python traceback.
    """
    attempts = 5
    for attempt in range(attempts):
        if not path.exists():
            break
        try:
            shutil.rmtree(path)
            break
        except PermissionError as exc:
            if attempt + 1 == attempts:
                raise AgentPackError(
                    AP3001,
                    f"cannot clean generated output '{path}': {exc.filename or path} is locked. "
                    "Close any app using the package, wait for antivirus scanning to finish, "
                    "then run 'agentpack clean' again.",
                ) from None
            time.sleep(0.5 * (attempt + 1))


def clean_dir(path: Path) -> None:
    """Replace a generated directory, tolerating brief Windows file locks."""
    remove_tree(path)
    path.mkdir(parents=True, exist_ok=True)
