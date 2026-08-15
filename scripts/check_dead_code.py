"""Enforce repository policy against dead code, orphan symbols, and invalid protocols."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
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


def check_repository(root: Path) -> list[Diagnostic]:
    """Scan the repository for dead code, orphan symbols, and invalid protocols."""
    src_dir = root / _SOURCE_ROOT
    if not src_dir.exists():
        return []

    all_py_files = [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts and "__scrap" not in p.parts
    ]
    file_word_counts: dict[Path, Counter[str]] = {}
    file_trees: dict[Path, ast.AST] = {}
    for p in all_py_files:
        try:
            content = p.read_text(encoding="utf-8")
            file_word_counts[p] = Counter(_WORD_PATTERN.findall(content))
            file_trees[p] = ast.parse(content, filename=str(p.relative_to(root)))
        except (OSError, UnicodeError, SyntaxError):
            continue

    src_files = [p for p in all_py_files if src_dir in p.parents or p == src_dir]
    diagnostics: list[Diagnostic] = []

    # 1. Protocol body checks
    for p in src_files:
        rel = p.relative_to(root).as_posix()
        tree = file_trees.get(p)
        if tree is not None:
            diagnostics.extend(_check_protocol_bodies(rel, tree))

    # 2. Unreferenced symbol checks in src
    for p in src_files:
        rel = p.relative_to(root).as_posix()
        tree = file_trees.get(p)
        if tree is None:
            continue

        for node in tree.body:  # type: ignore[attr-defined]
            # Check top-level functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fname = node.name
                if fname.startswith("__") and fname.endswith("__"):
                    continue
                decs = _decorator_names(node.decorator_list)
                if decs.intersection(_FRAMEWORK_DECORATORS):
                    continue

                total_refs = 0
                for other_p, counts in file_word_counts.items():
                    c = counts.get(fname, 0)
                    if other_p == p:
                        c = max(0, c - 1)
                    total_refs += c

                if total_refs == 0:
                    diagnostics.append(
                        Diagnostic(
                            rel,
                            node.lineno,
                            node.col_offset + 1,
                            "DED001",
                            f"function '{fname}' is defined but never referenced anywhere",
                        )
                    )

            # Check classes and their methods
            elif isinstance(node, ast.ClassDef):
                cname = node.name
                if not (cname.startswith("__") and cname.endswith("__")):
                    c_decs = _decorator_names(node.decorator_list)
                    if not c_decs.intersection(_FRAMEWORK_DECORATORS):
                        total_refs = 0
                        for other_p, counts in file_word_counts.items():
                            c = counts.get(cname, 0)
                            if other_p == p:
                                c = max(0, c - 1)
                            total_refs += c
                        if total_refs == 0:
                            diagnostics.append(
                                Diagnostic(
                                    rel,
                                    node.lineno,
                                    node.col_offset + 1,
                                    "DED001",
                                    f"class '{cname}' is defined but never referenced anywhere",
                                )
                            )

                # Check methods within classes
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mname = item.name
                        if mname.startswith("__") and mname.endswith("__"):
                            continue
                        if mname in _KNOWN_POLYMORPHIC_METHODS:
                            continue
                        m_decs = _decorator_names(item.decorator_list)
                        if m_decs.intersection(_FRAMEWORK_DECORATORS):
                            continue

                        # Check if method is called anywhere
                        total_refs = 0
                        for other_p, counts in file_word_counts.items():
                            c = counts.get(mname, 0)
                            if other_p == p:
                                c = max(0, c - 1)
                            total_refs += c

                        if total_refs == 0:
                            diagnostics.append(
                                Diagnostic(
                                    rel,
                                    item.lineno,
                                    item.col_offset + 1,
                                    "DED001",
                                    f"method '{node.name}.{mname}' is defined but never referenced anywhere",
                                )
                            )

    return sorted(diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the dead code policy checker CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPOSITORY_ROOT,
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
