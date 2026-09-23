"""Validate maintained documentation structure, links, indexes, and ADRs."""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_DOCUMENTS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("PLAN.md"),
    Path("SPEC.md"),
    Path("AGENTS.md"),
    Path("docs/00-design-index.md"),
    Path("docs/decisions/TEMPLATE.md"),
    Path("frontend/README.md"),
)
_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)")
_REFERENCE_LINK_PATTERN = re.compile(r"^[ \t]{0,3}\[[^\]]+\]:[ \t]*(?P<target><[^>]+>|\S+)")
_NUMBERED_DOCUMENT_PATTERN = re.compile(r"^(?P<number>\d{2})-[a-z0-9][a-z0-9-]*\.md$")
_ADR_PATTERN = re.compile(r"^ADR-(?P<number>\d{4})-[a-z0-9][a-z0-9-]*\.md$")
_ADR_TITLE_PATTERN = re.compile(r"^# ADR-(?P<number>\d{4}): \S.*$")
_ADR_SECTION_LEVEL = 2
_ADR_STATUS_PATTERN = re.compile(r"^\*\*Status:\*\* (?:Proposed|Accepted|Superseded|Deprecated)$")
_ALLOWED_EXTERNAL_SCHEMES = {"http", "https", "mailto"}


@dataclass(frozen=True, order=True)
class Diagnostic:
    """One deterministic documentation diagnostic."""

    path: str
    line: int
    code: str
    message: str

    def render(self) -> str:
        """Render the diagnostic in compiler-compatible form."""
        return f"{self.path}:{self.line}: {self.code} {self.message}"


@dataclass(frozen=True)
class MarkdownDocument:
    """Parsed Markdown facts needed by repository policy checks."""

    headings: tuple[tuple[int, str, int], ...]
    links: tuple[tuple[str, int], ...]
    first_content_line: int | None
    unclosed_fence_line: int | None
    unclosed_front_matter: bool


def _parse_markdown(text: str) -> MarkdownDocument:
    lines = text.splitlines()
    front_matter_end = 0
    unclosed_front_matter = False
    if lines and lines[0].strip() == "---":
        front_matter_end = next(
            (
                line_number
                for line_number, line in enumerate(lines[1:], start=2)
                if line.strip() == "---"
            ),
            0,
        )
        unclosed_front_matter = front_matter_end == 0

    headings: list[tuple[int, str, int]] = []
    links: list[tuple[str, int]] = []
    first_content_line: int | None = None
    fence_character: str | None = None
    fence_length = 0
    fence_line: int | None = None

    for line_number, line in enumerate(lines, start=1):
        if front_matter_end and line_number <= front_matter_end:
            continue

        stripped = line.strip()
        if first_content_line is None and stripped:
            first_content_line = line_number

        fence_match = _FENCE_PATTERN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
                fence_line = line_number
                continue
            if marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
                fence_line = None
                continue

        if fence_character is not None:
            continue

        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            headings.append((len(heading_match.group(1)), heading_match.group(2), line_number))

        for link_match in _LINK_PATTERN.finditer(line):
            target = link_match.group("target")
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            links.append((target, line_number))

        reference_match = _REFERENCE_LINK_PATTERN.match(line)
        if reference_match:
            target = reference_match.group("target")
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            links.append((target, line_number))

    return MarkdownDocument(
        headings=tuple(headings),
        links=tuple(links),
        first_content_line=first_content_line,
        unclosed_fence_line=fence_line,
        unclosed_front_matter=unclosed_front_matter,
    )


def _maintained_document_paths(root: Path) -> tuple[list[Path], list[Diagnostic]]:
    paths: list[Path] = []
    diagnostics: list[Diagnostic] = []
    for relative_path in _REQUIRED_DOCUMENTS:
        path = root / relative_path
        if path.is_file():
            paths.append(path)
        else:
            diagnostics.append(
                Diagnostic(relative_path.as_posix(), 1, "DOC001", "required document is missing")
            )

    docs_root = root / "docs"
    if docs_root.is_dir():
        paths.extend(sorted(docs_root.rglob("*.md")))
    else:
        diagnostics.append(Diagnostic("docs", 1, "DOC001", "documentation directory is missing"))

    return sorted(set(paths)), diagnostics


def _check_local_link(root: Path, path: Path, target: str, line: int) -> Diagnostic | None:
    relative_path = path.relative_to(root).as_posix()
    if target.startswith("#"):
        return None

    parsed_target = urlsplit(target)
    if parsed_target.scheme in _ALLOWED_EXTERNAL_SCHEMES:
        return None
    if parsed_target.scheme:
        return Diagnostic(
            relative_path,
            line,
            "DOC201",
            f"unsupported link scheme '{parsed_target.scheme}'; use a portable relative or HTTPS link",
        )
    if target.startswith(("/", "\\")):
        return Diagnostic(
            relative_path,
            line,
            "DOC201",
            f"local link must be relative: {target}",
        )

    decoded_path = unquote(parsed_target.path)
    if not decoded_path:
        return None

    resolved_root = root.resolve()
    resolved_target = (path.parent / decoded_path).resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        return Diagnostic(
            relative_path,
            line,
            "DOC201",
            f"local link escapes the repository: {target}",
        )

    if not resolved_target.exists():
        return Diagnostic(
            relative_path,
            line,
            "DOC202",
            f"local link target does not exist: {target}",
        )
    return None


def check_markdown_file(root: Path, path: Path) -> tuple[MarkdownDocument, list[Diagnostic]]:
    """Parse one maintained Markdown file and return its policy diagnostics."""
    relative_path = path.relative_to(root).as_posix()
    try:
        document = _parse_markdown(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        empty = MarkdownDocument(
            headings=(),
            links=(),
            first_content_line=None,
            unclosed_fence_line=None,
            unclosed_front_matter=False,
        )
        return empty, [Diagnostic(relative_path, 1, "DOC002", f"cannot read document: {error}")]

    diagnostics: list[Diagnostic] = []
    h1_headings = [heading for heading in document.headings if heading[0] == 1]
    if len(h1_headings) != 1:
        diagnostics.append(
            Diagnostic(
                relative_path,
                1,
                "DOC101",
                f"maintained documents require exactly one H1; found {len(h1_headings)}",
            )
        )
    elif document.first_content_line != h1_headings[0][2]:
        diagnostics.append(
            Diagnostic(
                relative_path, h1_headings[0][2], "DOC102", "H1 must be the first content line"
            )
        )

    previous_level = 0
    for level, _title, line in document.headings:
        if previous_level and level > previous_level + 1:
            diagnostics.append(
                Diagnostic(
                    relative_path,
                    line,
                    "DOC103",
                    f"heading level jumps from H{previous_level} to H{level}",
                )
            )
        previous_level = level

    if document.unclosed_fence_line is not None:
        diagnostics.append(
            Diagnostic(
                relative_path,
                document.unclosed_fence_line,
                "DOC104",
                "fenced code block is not closed",
            )
        )

    if document.unclosed_front_matter:
        diagnostics.append(
            Diagnostic(
                relative_path,
                1,
                "DOC105",
                "YAML front matter is not closed",
            )
        )

    for target, line in document.links:
        diagnostic = _check_local_link(root, path, target, line)
        if diagnostic is not None:
            diagnostics.append(diagnostic)

    return document, diagnostics


def _numbered_paths(
    paths: Iterable[Path],
    pattern: re.Pattern[str],
    root: Path,
    code: str,
    start: int,
    *,
    require_contiguous: bool = True,
) -> tuple[list[Path], list[Diagnostic]]:
    numbered: list[tuple[int, Path]] = []
    diagnostics: list[Diagnostic] = []
    used_numbers: dict[int, Path] = {}
    for path in paths:
        match = pattern.fullmatch(path.name)
        if match is None:
            continue
        number = int(match.group("number"))
        previous = used_numbers.get(number)
        if previous is not None:
            diagnostics.append(
                Diagnostic(
                    path.relative_to(root).as_posix(),
                    1,
                    code,
                    f"number {number:0{len(match.group('number'))}d} is also used by "
                    f"{previous.relative_to(root).as_posix()}",
                )
            )
        else:
            used_numbers[number] = path
        numbered.append((number, path))

    numbered.sort()
    if numbered and require_contiguous:
        actual = sorted({number for number, _path in numbered})
        expected = list(range(start, max(actual) + 1))
        if actual != expected:
            missing = sorted(set(expected) - set(actual))
            diagnostics.append(
                Diagnostic(
                    numbered[0][1].parent.relative_to(root).as_posix(),
                    1,
                    code,
                    f"numbering must be contiguous; missing {', '.join(str(number) for number in missing)}",
                )
            )

    return [path for _number, path in numbered], diagnostics


def _check_design_index(
    root: Path, numbered_docs: Sequence[Path], parsed: dict[Path, MarkdownDocument]
) -> list[Diagnostic]:
    index_path = root / "docs/00-design-index.md"
    index = parsed.get(index_path)
    if index is None:
        return []

    linked_docs: set[Path] = set()
    for target, _line in index.links:
        parsed_target = urlsplit(target)
        if parsed_target.scheme or not parsed_target.path:
            continue
        resolved = (index_path.parent / unquote(parsed_target.path)).resolve()
        if resolved in numbered_docs and resolved != index_path.resolve():
            linked_docs.add(resolved)

    expected = {path.resolve() for path in numbered_docs if path.resolve() != index_path.resolve()}
    return [
        Diagnostic(
            "docs/00-design-index.md",
            1,
            "DOC301",
            f"numbered design document is not linked: {missing_path.relative_to(root).as_posix()}",
        )
        for missing_path in sorted(expected - linked_docs)
    ]


def _check_adrs(
    root: Path, adr_paths: Sequence[Path], parsed: dict[Path, MarkdownDocument]
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    required_sections = ("Context", "Decision", "Consequences")
    for path in adr_paths:
        relative_path = path.relative_to(root).as_posix()
        filename_match = _ADR_PATTERN.fullmatch(path.name)
        document = parsed.get(path)
        if filename_match is None or document is None:
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue

        expected_number = filename_match.group("number")
        title_match = _ADR_TITLE_PATTERN.fullmatch(lines[0]) if lines else None
        if title_match is None or title_match.group("number") != expected_number:
            diagnostics.append(
                Diagnostic(
                    relative_path,
                    1,
                    "DOC501",
                    f"ADR title must start '# ADR-{expected_number}: '",
                )
            )

        status_lines = [
            (line_number, line)
            for line_number, line in enumerate(lines, start=1)
            if line.startswith("**Status:**")
        ]
        if len(status_lines) != 1 or _ADR_STATUS_PATTERN.fullmatch(status_lines[0][1]) is None:
            line = status_lines[0][0] if status_lines else 1
            diagnostics.append(
                Diagnostic(
                    relative_path,
                    line,
                    "DOC502",
                    "ADR requires one status: Proposed, Accepted, Superseded, or Deprecated",
                )
            )

        sections = [
            (title, line) for level, title, line in document.headings if level == _ADR_SECTION_LEVEL
        ]
        section_titles = [title for title, _line in sections]
        positions: list[int] = []
        for required in required_sections:
            try:
                positions.append(section_titles.index(required))
            except ValueError:
                diagnostics.append(
                    Diagnostic(
                        relative_path,
                        1,
                        "DOC503",
                        f"ADR is missing required '## {required}' section",
                    )
                )
        if len(positions) == len(required_sections) and positions != sorted(positions):
            diagnostics.append(
                Diagnostic(
                    relative_path,
                    1,
                    "DOC504",
                    "ADR sections must be ordered Context, Decision, Consequences",
                )
            )

    return diagnostics


def check_repository(root: Path) -> list[Diagnostic]:
    """Return all documentation-policy diagnostics for a repository tree."""
    root = root.resolve()
    document_paths, diagnostics = _maintained_document_paths(root)
    parsed: dict[Path, MarkdownDocument] = {}
    for path in document_paths:
        document, file_diagnostics = check_markdown_file(root, path)
        parsed[path] = document
        diagnostics.extend(file_diagnostics)

    docs_root = root / "docs"
    docs_paths = sorted(docs_root.glob("*.md")) if docs_root.is_dir() else []
    diagnostics.extend(
        Diagnostic(
            path.relative_to(root).as_posix(),
            1,
            "DOC302",
            "numbered design-document filename must use NN-kebab-case.md",
        )
        for path in docs_paths
        if re.match(r"^\d{2}", path.name)
        and _NUMBERED_DOCUMENT_PATTERN.fullmatch(path.name) is None
    )
    numbered_docs, numbering_diagnostics = _numbered_paths(
        docs_paths,
        _NUMBERED_DOCUMENT_PATTERN,
        root,
        "DOC302",
        0,
        require_contiguous=False,
    )
    diagnostics.extend(numbering_diagnostics)

    decisions_root = docs_root / "decisions"
    decision_paths = sorted(decisions_root.glob("*.md")) if decisions_root.is_dir() else []
    diagnostics.extend(
        Diagnostic(
            path.relative_to(root).as_posix(),
            1,
            "DOC505",
            "numbered ADR filename must use ADR-NNNN-kebab-case.md",
        )
        for path in decision_paths
        if path.name.startswith("ADR-") and _ADR_PATTERN.fullmatch(path.name) is None
    )
    adr_paths, adr_numbering_diagnostics = _numbered_paths(
        decision_paths,
        _ADR_PATTERN,
        root,
        "DOC505",
        1,
    )
    diagnostics.extend(adr_numbering_diagnostics)
    diagnostics.extend(_check_design_index(root, numbered_docs, parsed))
    diagnostics.extend(_check_adrs(root, adr_paths, parsed))
    return sorted(diagnostics)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the repository documentation policy check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)

    diagnostics = check_repository(args.root)
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.render())
        return 1

    print("Documentation policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
