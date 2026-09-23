"""Enforce repository policy against dead code, orphan symbols, and invalid protocols."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = Path("src/gendertagger")

_FRAMEWORK_DECORATORS = {
    "field_validator",
    "model_validator",
    "validator",
    "computed_field",
    "property",
    "abstractmethod",
    "override",
    "classmethod",
    "staticmethod",
    "task",
    "shared_task",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "options",
    "head",
    "api_route",
    "contextmanager",
    "asynccontextmanager",
}

_KNOWN_POLYMORPHIC_METHODS = {
    "construct_mapping",
    "dispatch",
    "authenticate",
}

_WORD_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True, order=True)
class Diagnostic:
    """One deterministic dead-code policy diagnostic."""

    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        """Render the diagnostic in compiler-compatible form."""
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"


def _decorator_names(decorator_list: Sequence[ast.expr]) -> set[str]:
    names: set[str] = set()
    for d in decorator_list:
        if isinstance(d, ast.Name):
            names.add(d.id)
        elif isinstance(d, ast.Attribute):
            names.add(d.attr)
        elif isinstance(d, ast.Call):
            if isinstance(d.func, ast.Name):
                names.add(d.func.id)
            elif isinstance(d.func, ast.Attribute):
                names.add(d.func.attr)
    return names


def _is_protocol_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Protocol":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Protocol":
            return True
    return False


def _check_protocol_bodies(
    relative_path: str,
    tree: ast.AST,
) -> list[Diagnostic]:
    return [
        Diagnostic(
            relative_path,
            stmt.lineno,
            stmt.col_offset + 1,
            "DED002",
            f"protocol method '{item.name}' must use '...' instead of 'raise NotImplementedError'",
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and _is_protocol_class(node)
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        for stmt in item.body
        if (
            isinstance(stmt, ast.Raise)
            and isinstance(stmt.exc, ast.Name)
            and stmt.exc.id == "NotImplementedError"
        )
    ]


def _is_exempt_definition(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    is_dunder = node.name.startswith("__") and node.name.endswith("__")
    return is_dunder or bool(_decorator_names(node.decorator_list) & _FRAMEWORK_DECORATORS)


def _reference_count(
    name: str,
    defining_path: Path,
    file_word_counts: Mapping[Path, Counter[str]],
) -> int:
    """Count word occurrences of ``name`` across all files, excluding its own definition."""
    total = 0
    for path, counts in file_word_counts.items():
        count = counts.get(name, 0)
        if path == defining_path:
            count = max(0, count - 1)
        total += count
    return total


def _unreferenced(
    relative_path: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    subject: str,
) -> Diagnostic:
    return Diagnostic(
        relative_path,
        node.lineno,
        node.col_offset + 1,
        "DED001",
        f"{subject} is defined but never referenced anywhere",
    )


def _unreferenced_methods(
    relative_path: str,
    path: Path,
    node: ast.ClassDef,
    file_word_counts: Mapping[Path, Counter[str]],
) -> list[Diagnostic]:
    return [
        _unreferenced(relative_path, item, f"method '{node.name}.{item.name}'")
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name not in _KNOWN_POLYMORPHIC_METHODS
        and not _is_exempt_definition(item)
        and _reference_count(item.name, path, file_word_counts) == 0
    ]


def _unreferenced_symbols(
    relative_path: str,
    path: Path,
    tree: ast.Module,
    file_word_counts: Mapping[Path, Counter[str]],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                not _is_exempt_definition(node)
                and _reference_count(node.name, path, file_word_counts) == 0
            ):
                diagnostics.append(_unreferenced(relative_path, node, f"function '{node.name}'"))
        elif isinstance(node, ast.ClassDef):
            if (
                not _is_exempt_definition(node)
                and _reference_count(node.name, path, file_word_counts) == 0
            ):
                diagnostics.append(_unreferenced(relative_path, node, f"class '{node.name}'"))
            diagnostics.extend(_unreferenced_methods(relative_path, path, node, file_word_counts))
    return diagnostics


def _load_python_sources(
    root: Path,
) -> tuple[list[Path], dict[Path, Counter[str]], dict[Path, ast.Module]]:
    all_py_files = [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts and "__scrap" not in p.parts
    ]
    file_word_counts: dict[Path, Counter[str]] = {}
    file_trees: dict[Path, ast.Module] = {}
    for p in all_py_files:
        try:
            content = p.read_text(encoding="utf-8")
            file_word_counts[p] = Counter(_WORD_PATTERN.findall(content))
            file_trees[p] = ast.parse(content, filename=str(p.relative_to(root)))
        except (OSError, UnicodeError, SyntaxError):
            continue
    return all_py_files, file_word_counts, file_trees


def check_repository(root: Path) -> list[Diagnostic]:
    """Scan the repository for dead code, orphan symbols, and invalid protocols."""
    src_dir = root / _SOURCE_ROOT
    if not src_dir.exists():
        return []

    all_py_files, file_word_counts, file_trees = _load_python_sources(root)
    src_files = [p for p in all_py_files if src_dir in p.parents or p == src_dir]
    diagnostics: list[Diagnostic] = []

    # 1. Protocol body checks
    for p in src_files:
        tree = file_trees.get(p)
        if tree is not None:
            diagnostics.extend(_check_protocol_bodies(p.relative_to(root).as_posix(), tree))

    # 2. Unreferenced symbol checks in src
    for p in src_files:
        tree = file_trees.get(p)
        if tree is not None:
            diagnostics.extend(
                _unreferenced_symbols(p.relative_to(root).as_posix(), p, tree, file_word_counts)
            )

    return sorted(diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the dead code policy checker CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=_BACKEND_ROOT,
        help="Repository root path to check",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success messages",
    )
    args = parser.parse_args(argv)

    diagnostics = check_repository(args.root.resolve())
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.render())
        return 1

    if not args.quiet:
        print("Dead code policy passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
