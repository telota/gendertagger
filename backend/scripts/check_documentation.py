"""Validate maintained documentation structure, links, indexes, and ADRs."""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_DOCUMENTS = (
    Path("README.md"),
    Path("QUICKSTART.md"),
    Path("CONTRIBUTING.md"),
    Path("SPEC.md"),
    Path("AGENTS.md"),
    Path("DESIGN.md"),
    Path("PRODUCT.md"),
    Path("IDEAS.md"),
    Path("audit.md"),
    Path("CHANGELOG.md"),
    Path("RELEASE_GAPS.md"),
    Path("backend/README.md"),
    Path("contracts/README.md"),
    Path("docs/00-design-index.md"),
    Path("docs/decisions/TEMPLATE.md"),
    Path("frontend/README.md"),
)
_ARCHIVAL_DOCUMENT_DIRECTORIES = (Path("docs/paper"), Path("docs/poster"))
_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_SETEXT_PATTERN = re.compile(r"^[ \t]{0,3}(=+|-+)[ \t]*$")
_FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)")
_REFERENCE_LINK_PATTERN = re.compile(r"^[ \t]{0,3}\[[^\]]+\]:[ \t]*(?P<target><[^>]+>|\S+)")
_NUMBERED_DOCUMENT_PATTERN = re.compile(r"^(?P<number>\d{2})-[a-z0-9][a-z0-9-]*\.md$")
_ADR_PATTERN = re.compile(r"^ADR-(?P<number>\d{4})-[a-z0-9][a-z0-9-]*\.md$")
_ADR_TITLE_PATTERN = re.compile(r"^# ADR-(?P<number>\d{4}): \S.*$")
_ADR_SECTION_LEVEL = 2
_ADR_STATUS_PATTERN = re.compile(r"^\*\*Status:\*\* (?:Proposed|Accepted|Superseded|Deprecated)$")
_ALLOWED_EXTERNAL_SCHEMES = {"http", "https", "mailto"}
_INVALID_PERCENT_PATTERN = re.compile(r"%(?![0-9a-fA-F]{2})")


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
    heading_ids: frozenset[str]
    links: tuple[tuple[str, int], ...]
    first_content_line: int | None
    unclosed_fence_line: int | None
    unclosed_front_matter: bool


def _code_span(text: str, start: int) -> tuple[str, int]:
    end_marker = start + 1
    while end_marker < len(text) and text[end_marker] == "`":
        end_marker += 1
    closing = next(
        (
            match
            for match in re.finditer(r"`+", text[end_marker:])
            if len(match.group()) == end_marker - start
        ),
        None,
    )
    if closing is None:
        return "", end_marker
    end = end_marker + closing.start()
    content = text[end_marker:end].replace("\n", " ")
    if content.startswith(" ") and content.endswith(" ") and content.strip():
        content = content[1:-1]
    return content, end_marker + closing.end()


def _heading_text(title: str) -> str:
    """Extract inline heading text before applying GitHub-style slug rules."""
    output: list[str] = []
    index = 0
    while index < len(title):
        character = title[index]
        if character == "\\" and index + 1 < len(title):
            output.append(f"&#{ord(title[index + 1])};")
            index += 2
        elif character == "`":
            content, index = _code_span(title, index)
            output.append(escape(content).replace("_", "&#95;"))
        elif character == "[" or title[index : index + 2] == "![":
            content, index = _heading_label(title, index)
            output.append(content)
        elif character == "<":
            end = title.find(">", index + 1)
            if end < 0:
                output.append(character)
                index += 1
            else:
                content = title[index + 1 : end]
                if content.startswith(("https://", "http://", "mailto:")):
                    output.append(content.removeprefix("mailto:"))
                index = end + 1
        else:
            output.append(character)
            index += 1
    return re.sub(r"(?<!\w)(_+)(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", "".join(output))


def _heading_label(title: str, index: int) -> tuple[str, int]:
    start = index + (2 if title[index] == "!" else 1)
    end = _closing_delimiter(title, start, "[", "]")
    if end is None:
        return title[index], index + 1
    label = _heading_text(title[start:end])
    index = end + 1
    if index < len(title) and title[index] in "([":
        opener = title[index]
        closer = ")" if opener == "(" else "]"
        end = _closing_delimiter(title, index + 1, opener, closer)
        if end is not None:
            index = end + 1
    return label, index


def _closing_delimiter(text: str, start: int, opener: str, closer: str) -> int | None:
    depth = 1
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == opener:
            depth += 1
        elif character == closer:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _heading_ids(headings: Sequence[tuple[int, str, int]]) -> frozenset[str]:
    generated: set[str] = set()
    for _level, title, _line in headings:
        # Keep Unicode letters/marks, decimal/letter numbers, and connector
        # punctuation. Symbols, other numbers, and non-ASCII separators vanish.
        base = "".join(
            "-" if character == " " else character
            for character in unescape(_heading_text(title)).lower()
            if character in " -"
            or character.isalpha()
            or unicodedata.category(character) in {"Mn", "Mc", "Me", "Nd", "Nl", "Pc"}
        )
        candidate = base
        suffix = 0
        while candidate in generated:
            suffix += 1
            candidate = f"{base}-{suffix}"
        generated.add(candidate)
    return frozenset(generated)


def _front_matter_boundary(lines: Sequence[str]) -> tuple[int, bool]:
    if not lines or lines[0].strip() != "---":
        return 0, False
    end = next(
        (number for number, line in enumerate(lines[1:], start=2) if line.strip() == "---"),
        0,
    )
    return end, end == 0


def _visible_markdown_lines(
    lines: Sequence[str], front_matter_end: int
) -> tuple[list[tuple[int, str]], int | None, int | None]:
    visible: list[tuple[int, str]] = []
    first_content_line: int | None = None
    fence_marker: str | None = None
    fence_line: int | None = None
    for line_number, line in enumerate(lines[front_matter_end:], start=front_matter_end + 1):
        if first_content_line is None and line.strip():
            first_content_line = line_number
        match = _FENCE_PATTERN.match(line)
        if fence_marker is not None:
            if (
                match
                and match.group(1)[0] == fence_marker[0]
                and len(match.group(1)) >= len(fence_marker)
                and not line[match.end() :].strip()
            ):
                fence_marker = None
                fence_line = None
            continue
        if match and not (match.group(1)[0] == "`" and "`" in line[match.end() :]):
            fence_marker = match.group(1)
            fence_line = line_number
            visible.append((line_number, ""))
            continue
        visible.append((line_number, line))
    return visible, first_content_line, fence_line


def _parse_headings(lines: Sequence[tuple[int, str]]) -> tuple[tuple[int, str, int], ...]:
    headings: list[tuple[int, str, int]] = []
    previous_text: tuple[str, int] | None = None
    for line_number, line in lines:
        stripped = line.strip()
        match = _HEADING_PATTERN.match(line)
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip()
            headings.append((len(match.group(1)), title, line_number))
            previous_text = None
        elif _SETEXT_PATTERN.fullmatch(line) and previous_text is not None:
            title, title_line = previous_text
            headings.append((1 if stripped.startswith("=") else 2, title, title_line))
            previous_text = None
        elif (
            not stripped
            or re.match(r"^(?: {4}|\t| {0,3}(?:>|[-+*] |[0-9]+[.)] |<))", line)
            or re.fullmatch(r"(?:[ \t]*[-*_]){3,}[ \t]*", line)
        ):
            previous_text = None
        elif previous_text is None:
            previous_text = (stripped, line_number)
        else:
            previous_text = (f"{previous_text[0]} {stripped}", previous_text[1])
    return tuple(headings)


def _parse_links(lines: Sequence[tuple[int, str]]) -> tuple[tuple[str, int], ...]:
    links: list[tuple[str, int]] = []
    for line_number, line in lines:
        matches = list(_LINK_PATTERN.finditer(line))
        reference_match = _REFERENCE_LINK_PATTERN.match(line)
        if reference_match:
            matches.append(reference_match)
        for match in matches:
            target = match.group("target")
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            links.append((target, line_number))
    return tuple(links)


def _parse_markdown(text: str) -> MarkdownDocument:
    lines = text.splitlines()
    front_matter_end, unclosed_front_matter = _front_matter_boundary(lines)
    visible, first_content_line, fence_line = (
        ([], None, None)
        if unclosed_front_matter
        else _visible_markdown_lines(lines, front_matter_end)
    )
    headings = _parse_headings(visible)
    return MarkdownDocument(
        headings=headings,
        heading_ids=_heading_ids(headings),
        links=_parse_links(visible),
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
        paths.extend(
            path
            for path in docs_root.rglob("*.md")
            if not any(
                path.is_relative_to(root / directory)
                for directory in _ARCHIVAL_DOCUMENT_DIRECTORIES
            )
        )
    else:
        diagnostics.append(Diagnostic("docs", 1, "DOC001", "documentation directory is missing"))

    return sorted(set(paths)), diagnostics


def _check_local_link(
    root: Path,
    path: Path,
    target: str,
    line: int,
    parsed: dict[Path, MarkdownDocument | None],
    diagnostics: list[Diagnostic],
) -> Diagnostic | None:
    relative_path = path.relative_to(root).as_posix()
    try:
        parsed_target = urlsplit(target)
    except ValueError as error:
        return Diagnostic(relative_path, line, "DOC201", f"invalid link: {target}: {error}")
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
        return Diagnostic(relative_path, line, "DOC201", f"local link must be relative: {target}")
    try:
        if _INVALID_PERCENT_PATTERN.search(parsed_target.path + parsed_target.fragment):
            raise ValueError("malformed percent escape")
        decoded_path = unquote(parsed_target.path, errors="strict")
        fragment = unquote(parsed_target.fragment, errors="strict")
        if "\0" in decoded_path:
            raise ValueError("NUL is not a file-path character")
    except (UnicodeError, ValueError) as error:
        return Diagnostic(
            relative_path, line, "DOC201", f"invalid local link encoding: {target}: {error}"
        )

    resolved_target = (path.parent / decoded_path).resolve() if decoded_path else path.resolve()
    try:
        resolved_target.relative_to(root.resolve())
    except ValueError:
        return Diagnostic(
            relative_path, line, "DOC201", f"local link escapes the repository: {target}"
        )
    if not resolved_target.exists():
        return Diagnostic(
            relative_path, line, "DOC202", f"local link target does not exist: {target}"
        )
    if not fragment or resolved_target.suffix.lower() != ".md":
        return None
    if not resolved_target.is_file():
        return Diagnostic(
            relative_path, line, "DOC203", f"Markdown heading target is not a file: {target}"
        )
    document = _load_markdown(root, resolved_target, parsed, diagnostics)
    if document is not None and fragment not in document.heading_ids:
        return Diagnostic(
            relative_path, line, "DOC203", f"Markdown heading fragment does not exist: {target}"
        )
    return None


def _load_markdown(
    root: Path,
    path: Path,
    parsed: dict[Path, MarkdownDocument | None],
    diagnostics: list[Diagnostic],
) -> MarkdownDocument | None:
    if path not in parsed:
        try:
            parsed[path] = _parse_markdown(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as error:
            parsed[path] = None
            diagnostics.append(
                Diagnostic(
                    path.relative_to(root).as_posix(), 1, "DOC002", f"cannot read document: {error}"
                )
            )
    return parsed[path]


def _check_document_structure(
    document: MarkdownDocument, root: Path, path: Path
) -> list[Diagnostic]:
    relative_path = path.relative_to(root).as_posix()

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

    return diagnostics


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
    root: Path, numbered_docs: Sequence[Path], parsed: dict[Path, MarkdownDocument | None]
) -> list[Diagnostic]:
    index_path = root / "docs/00-design-index.md"
    index = parsed.get(index_path)
    if index is None:
        return []

    linked_docs: set[Path] = set()
    for target, _line in index.links:
        try:
            parsed_target = urlsplit(target)
            resolved = (index_path.parent / unquote(parsed_target.path)).resolve()
        except ValueError:
            continue
        if parsed_target.scheme or not parsed_target.path:
            continue
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
    root: Path, adr_paths: Sequence[Path], parsed: dict[Path, MarkdownDocument | None]
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
    parsed: dict[Path, MarkdownDocument | None] = {}
    for path in document_paths:
        document = _load_markdown(root, path, parsed, diagnostics)
        if document is not None:
            diagnostics.extend(_check_document_structure(document, root, path))
    for path in document_paths:
        document = parsed.get(path)
        if document is None:
            continue
        for target, line in document.links:
            diagnostic = _check_local_link(root, path, target, line, parsed, diagnostics)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

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
