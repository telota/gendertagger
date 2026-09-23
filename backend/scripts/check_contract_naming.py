"""Validate semantic naming rules for canonical contract fields."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_ROOTS = (
    Path("src/gendertagger/config"),
    Path("src/gendertagger/models"),
)
_COLLECTION_ANNOTATIONS = {
    "Collection",
    "FrozenSet",
    "Iterable",
    "Iterator",
    "List",
    "Sequence",
    "Set",
    "Tuple",
    "collection",
    "frozenset",
    "iterable",
    "iterator",
    "list",
    "sequence",
    "set",
    "tuple",
}
_DECLARATION_ANNOTATIONS = {"ClassVar", "Final"}
_NUMERIC_ANNOTATIONS = {"Decimal", "float", "int"}
_OPTIONAL_ANNOTATIONS = {"Optional", "Union"}
_UNIT_SUFFIXES = (
    "_days",
    "_hours",
    "_microseconds",
    "_milliseconds",
    "_minutes",
    "_nanoseconds",
    "_seconds",
)
_UNITLESS_DURATION_SUFFIXES = ("_delay", "_duration", "_interval", "_timeout", "_ttl")


@dataclass(frozen=True, order=True)
class Diagnostic:
    """One deterministic contract-naming diagnostic."""

    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        """Render the diagnostic in compiler-compatible form."""
        return f"{self.path}:{self.line}:{self.column}: {self.code} {self.message}"


def _annotation_name(annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return None


def _annotation_members(annotation: ast.expr) -> Iterable[ast.expr]:
    if isinstance(annotation, ast.Subscript) and _annotation_name(annotation.value) == "Annotated":
        if isinstance(annotation.slice, ast.Tuple) and annotation.slice.elts:
            yield from _annotation_members(annotation.slice.elts[0])
        else:
            yield from _annotation_members(annotation.slice)
        return

    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        yield from _annotation_members(annotation.left)
        yield from _annotation_members(annotation.right)
        return

    if (
        isinstance(annotation, ast.Subscript)
        and _annotation_name(annotation.value) in _OPTIONAL_ANNOTATIONS
    ):
        if isinstance(annotation.slice, ast.Tuple):
            for member in annotation.slice.elts:
                yield from _annotation_members(member)
        else:
            yield from _annotation_members(annotation.slice)
        return

    yield annotation


def _is_direct_type(annotation: ast.expr, expected: set[str]) -> bool:
    return any(
        _annotation_name(member) in expected
        for member in _annotation_members(annotation)
        if not (isinstance(member, ast.Constant) and member.value is None)
    )


def _collection_item(annotation: ast.expr) -> ast.expr | None:
    members = [
        member
        for member in _annotation_members(annotation)
        if not (isinstance(member, ast.Constant) and member.value is None)
    ]
    if len(members) != 1:
        return None

    member = members[0]
    if not isinstance(member, ast.Subscript):
        return None
    if _annotation_name(member.value) not in _COLLECTION_ANNOTATIONS:
        return None

    if isinstance(member.slice, ast.Tuple):
        return member.slice.elts[0] if member.slice.elts else None
    return member.slice


def _is_declaration(annotation: ast.expr) -> bool:
    return (
        isinstance(annotation, ast.Subscript)
        and _annotation_name(annotation.value) in _DECLARATION_ANNOTATIONS
    )


def _field_diagnostics(path: str, field: ast.AnnAssign) -> list[Diagnostic]:
    if not isinstance(field.target, ast.Name) or field.target.id.startswith("_"):
        return []
    if _is_declaration(field.annotation):
        return []

    name = field.target.id
    location = (path, field.target.lineno, field.target.col_offset + 1)
    diagnostics: list[Diagnostic] = []

    if name == "confidence":
        diagnostics.append(
            Diagnostic(
                *location,
                "GTN001",
                "contract field 'confidence' is ambiguous; use method_confidence, "
                "agreement_score, or certainty_tier",
            )
        )

    if _is_direct_type(field.annotation, {"datetime"}) and not name.endswith("_at"):
        diagnostics.append(
            Diagnostic(
                *location,
                "GTN002",
                "datetime contract fields must end in '_at'",
            )
        )

    uuid_item = _collection_item(field.annotation)
    if _is_direct_type(field.annotation, {"UUID"}) and name != "id" and not name.endswith("_id"):
        diagnostics.append(
            Diagnostic(
                *location,
                "GTN003",
                "UUID contract fields must be named 'id' or end in '_id'",
            )
        )
    elif (
        uuid_item is not None and _is_direct_type(uuid_item, {"UUID"}) and not name.endswith("_ids")
    ):
        diagnostics.append(
            Diagnostic(
                *location,
                "GTN003",
                "UUID collection contract fields must end in '_ids'",
            )
        )

    is_unitless_duration = name in {suffix[1:] for suffix in _UNITLESS_DURATION_SUFFIXES} or any(
        name.endswith(suffix) for suffix in _UNITLESS_DURATION_SUFFIXES
    )
    if (
        is_unitless_duration
        and _is_direct_type(field.annotation, _NUMERIC_ANNOTATIONS)
        and not name.endswith(_UNIT_SUFFIXES)
    ):
        diagnostics.append(
            Diagnostic(
                *location,
                "GTN004",
                "numeric duration contract fields must include a unit suffix such as '_seconds'",
            )
        )

    return diagnostics


def check_tree(root: Path) -> list[Diagnostic]:
    """Return semantic naming diagnostics below the configured contract roots."""
    diagnostics: list[Diagnostic] = []
    for relative_root in _CONTRACT_ROOTS:
        contract_root = root / relative_root
        if not contract_root.is_dir():
            continue
        for source_path in sorted(contract_root.rglob("*.py")):
            relative_path = source_path.relative_to(root).as_posix()
            try:
                tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=relative_path)
            except (OSError, UnicodeError, SyntaxError) as error:
                line = error.lineno if isinstance(error, SyntaxError) and error.lineno else 1
                column = error.offset if isinstance(error, SyntaxError) and error.offset else 1
                diagnostics.append(
                    Diagnostic(relative_path, line, column, "GTN000", f"cannot parse file: {error}")
                )
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for statement in node.body:
                    if isinstance(statement, ast.AnnAssign):
                        diagnostics.extend(_field_diagnostics(relative_path, statement))

    return sorted(diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the contract-naming policy check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_BACKEND_ROOT)
    args = parser.parse_args(argv)

    diagnostics = check_tree(args.root.resolve())
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.render())
        return 1

    print("Contract naming policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
