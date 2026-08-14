"""Reject sensitive or local-only files from built distributions."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

_FORBIDDEN_ROOTS = {
    ".agents",
    ".codex",
    ".git",
    ".gitlab",
    ".venv",
    "__scrap",
    "artifacts",
    "build",
    "data",
    "dist",
    "node_modules",
    "output",
}
_FORBIDDEN_SUFFIXES = {
    ".bin",
    ".db",
    ".h5",
    ".joblib",
    ".parquet",
    ".pkl",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}


def _archive_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()

    if path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        with tarfile.open(path, mode="r:*") as archive:
            return archive.getnames()

    msg = f"unsupported distribution archive: {path}"
    raise ValueError(msg)


def _relative_parts(member: str) -> tuple[str, ...]:
    parts = tuple(part for part in PurePosixPath(member).parts if part not in {"", "."})
    if parts and parts[0].startswith("gendertagger-"):
        return parts[1:]
    return parts


def _is_forbidden(member: str) -> bool:
    parts = _relative_parts(member)
    if not parts:
        return False
    if any(part in _FORBIDDEN_ROOTS for part in parts):
        return True

    filename = parts[-1]
    return (
        filename == ".env"
        or filename.startswith(".env.")
        or PurePosixPath(filename).suffix.lower() in _FORBIDDEN_SUFFIXES
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate every distribution archive supplied on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args(argv)

    violations = [
        f"{archive}: {member}"
        for archive in args.archives
        for member in _archive_members(archive)
        if _is_forbidden(member)
    ]
    if violations:
        print("Forbidden distribution members found:")
        for violation in sorted(violations):
            print(f"  {violation}")
        return 1

    print(f"Distribution policy passed for {len(args.archives)} archive(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
