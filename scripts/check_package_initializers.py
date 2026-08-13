"""Require explicit, docstring-only Python package initializers."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOTS = (Path("src/gendertagger"),)


@dataclass(frozen=True, order=True)
class Diagnostic:
    """One deterministic package-initializer diagnostic."""

    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        """Render the diagnostic in compiler-compatible form."""
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _check_initializer(root: Path, path: Path) -> list[Diagnostic]:
    relative_path = path.relative_to(root).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
    except (OSError, UnicodeError, SyntaxError) as error:
        line = error.lineno if isinstance(error, SyntaxError) and error.lineno else 1
        column = error.offset if isinstance(error, SyntaxError) and error.offset else 1
        return [
            Diagnostic(relative_path, line, column, "PKG001", f"cannot parse initializer: {error}")
        ]

    diagnostics: list[Diagnostic] = []
    if not tree.body or not _is_docstring(tree.body[0]):
        diagnostics.append(
            Diagnostic(
                relative_path,
                1,
                1,
                "PKG101",
                "package initializer must begin with a module docstring",
            )
        )

    for statement in tree.body:
        if _is_docstring(statement) and statement is tree.body[0]:
            continue
        diagnostics.append(
            Diagnostic(
                relative_path,
                statement.lineno,
                statement.col_offset + 1,
                "PKG102",
                "package initializer must contain only its module docstring; "
                "import from the defining module instead",
            )
        )
    return diagnostics


def check_tree(root: Path) -> list[Diagnostic]:
    """Return package-initializer policy diagnostics for a repository tree."""
    root = root.resolve()
    diagnostics: list[Diagnostic] = []
    for relative_package_root in _PACKAGE_ROOTS:
        package_root = root / relative_package_root
        if not package_root.is_dir():
            diagnostics.append(
                Diagnostic(
                    relative_package_root.as_posix(),
                    1,
                    1,
                    "PKG001",
                    "configured package root is missing",
                )
            )
            continue

        for initializer in sorted(package_root.rglob("__init__.py")):
            diagnostics.extend(_check_initializer(root, initializer))

        source_directories = {
            source_file.parent
            for source_file in package_root.rglob("*.py")
            if source_file.name != "__init__.py"
        }
        source_directories.add(package_root)
        for source_directory in sorted(source_directories):
            initializer = source_directory / "__init__.py"
            if initializer.is_file():
                continue
            diagnostics.append(
                Diagnostic(
                    initializer.relative_to(root).as_posix(),
                    1,
                    1,
                    "PKG103",
                    "source package requires an explicit __init__.py marker",
                )
            )

    return sorted(diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the package-initializer policy check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)

    diagnostics = check_tree(args.root)
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.render())
        return 1

    print("Package initializer policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
