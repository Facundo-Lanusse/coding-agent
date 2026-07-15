"""Contained, deterministic reset of the FastAPI demo fixture."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


class FixtureResetError(Exception):
    code = "fixture_reset_error"


@dataclass(frozen=True, slots=True)
class FixtureSnapshot:
    workspace: Path
    checksum: str
    files: tuple[str, ...]


class FixtureResetter:
    """Copy an immutable seed into one direct child of an allowed runtime root."""

    def __init__(self, seed_root: str | Path, runtime_root: str | Path) -> None:
        self._seed = Path(seed_root).resolve()
        self._runtime = Path(runtime_root).resolve()
        if not self._seed.is_dir():
            raise FixtureResetError(f"Demo seed does not exist: {self._seed}.")
        self._runtime.mkdir(parents=True, exist_ok=True)
        if self._runtime == self._seed or self._runtime in self._seed.parents:
            raise FixtureResetError("Runtime root cannot contain or equal the immutable seed.")

    def reset(self, name: str) -> FixtureSnapshot:
        if not name or name in {".", ".."} or Path(name).name != name:
            raise FixtureResetError("Workspace name must be one safe path component.")
        destination = (self._runtime / name).resolve(strict=False)
        if destination.parent != self._runtime:
            raise FixtureResetError("Demo workspace must be a direct child of runtime root.")
        if destination.is_symlink():
            raise FixtureResetError("Demo workspace cannot be a symlink.")

        nonce = uuid.uuid4().hex
        staging = self._runtime / f".{name}.staging-{nonce}"
        backup = self._runtime / f".{name}.backup-{nonce}"
        try:
            shutil.copytree(self._seed, staging, symlinks=False)
            if destination.exists():
                os.replace(destination, backup)
            os.replace(staging, destination)
        except OSError as exc:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise FixtureResetError(f"Demo fixture reset failed ({type(exc).__name__}).") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        if backup.exists():
            shutil.rmtree(backup)
        return snapshot(destination)


def snapshot(root: str | Path) -> FixtureSnapshot:
    canonical = Path(root).resolve()
    if not canonical.is_dir():
        raise FixtureResetError("Cannot fingerprint a missing demo workspace.")
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(canonical.rglob("*")):
        if path.is_symlink():
            raise FixtureResetError("Fixture snapshots reject symlinks.")
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(canonical).as_posix()
        files.append(relative)
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return FixtureSnapshot(workspace=canonical, checksum=digest.hexdigest(), files=tuple(files))

