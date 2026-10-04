from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_ROOT = _REPOSITORY_ROOT / "scripts"


def _run_policy(script_name: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the interpreter and script paths are repository-controlled.
        [sys.executable, str(_SCRIPTS_ROOT / script_name), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_minimal_documentation(root: Path) -> None:
    for name in (
        "README.md",
        "QUICKSTART.md",
        "CONTRIBUTING.md",
        "SPEC.md",
        "AGENTS.md",
        "DESIGN.md",
        "PRODUCT.md",
        "IDEAS.md",
        "audit.md",
        "CHANGELOG.md",
        "RELEASE_GAPS.md",
        "backend/README.md",
        "contracts/README.md",
    ):
        _write(root / name, f"# {Path(name).stem}\n")
    _write(root / "frontend/README.md", "# Frontend\n")
    _write(
        root / "docs/00-design-index.md",
        "# Design document index\n\n[Topic](01-topic.md)\n",
    )
    _write(root / "docs/01-topic.md", "# Topic\n")
    _write(root / "docs/decisions/TEMPLATE.md", "# ADR-NNNN: Short decision title\n")
    _write(
        root / "docs/decisions/ADR-0001-example.md",
        """# ADR-0001: Example

**Status:** Accepted

## Context

Context.

## Decision

Decision.

## Consequences

Consequences.
""",
    )


def test_documentation_policy_accepts_a_complete_repository(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "relative_path",
    [
        "DESIGN.md",
        "PRODUCT.md",
        "IDEAS.md",
        "audit.md",
        "CHANGELOG.md",
        "RELEASE_GAPS.md",
        "backend/README.md",
        "contracts/README.md",
    ],
)
def test_documentation_policy_requires_maintained_inventory(
    tmp_path: Path, relative_path: str
) -> None:
    _write_minimal_documentation(tmp_path)
    (tmp_path / relative_path).unlink()

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout == f"{relative_path}:1: DOC001 required document is missing\n"


@pytest.mark.parametrize(
    "relative_path",
    [
        "DESIGN.md",
        "PRODUCT.md",
        "IDEAS.md",
        "audit.md",
        "CHANGELOG.md",
        "RELEASE_GAPS.md",
        "backend/README.md",
        "contracts/README.md",
    ],
)
def test_documentation_policy_checks_newly_maintained_root_documents(
    tmp_path: Path, relative_path: str
) -> None:
    _write_minimal_documentation(tmp_path)
    _write(tmp_path / relative_path, "# Maintained\n\n[Broken](#absent)\n")

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout == (
        f"{relative_path}:3: DOC203 Markdown heading fragment does not exist: #absent\n"
    )


def test_documentation_policy_accepts_rendered_heading_fragments(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        """---
title: Metadata
---
# Topic

## Über **Café**!

## _Résumé_ and [中文](https://example.invalid/unknown)

## `raw_key` &amp; <em>value</em>

## Keep in_word and under_score

## Foo

## Foo

## Foo-1

## Foo

Setext
title
------

   ## Indented ATX ###

## `__literal__` and ``a ` b``

## A—B (v2): C/D + E

## Straße \u0399 Αθήνα 日本語 \u0661

## Café

## Café

[Unicode](#über-café)
[Encoded Unicode](#%C3%BCber-caf%C3%A9)
[Rendered link](#résumé-and-中文)
[Code and HTML](#raw_key--value)
[Underscores](#keep-in_word-and-under_score)
[First](#foo)
[Repeated](#foo-1)
[Collision](#foo-1-1)
[After collision](#foo-2)
[Setext](#setext-title)
[ATX](#indented-atx)
[Code delimiters](#__literal__-and-a--b)
[Punctuation](#ab-v2-cd--e)
[Multiscript](#straße-\u03b9-αθήνα-日本語-\u0661)
[Composed](#café)
[Decomposed](#cafe%CC%81)
[Top](#)
""",
    )
    _write(
        tmp_path / "README.md",
        "# Readme\n\n[Cross-file](docs/01-topic.md#%C3%BCber-caf%C3%A9)\n"
        "[Reference][topic]\n\n[topic]: docs/01-topic.md#foo-1-1\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "fragment",
    ["foo-3", "foo-1-2", "Foo", "caf%C3%A8", "caf%25C3%25A9", "custom-id"],
)
def test_documentation_policy_rejects_nonexistent_or_noncanonical_fragments(
    tmp_path: Path, fragment: str
) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        '# Topic\n\n## Foo\n\n## Foo\n\n## Foo-1\n\n## Foo\n\n## Café\n\n<a id="custom-id"></a>\n',
    )
    _write(
        tmp_path / "README.md",
        f"# Readme\n\n[Cross-file](docs/01-topic.md#{fragment})\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout == (
        "README.md:3: DOC203 Markdown heading fragment does not exist: "
        f"docs/01-topic.md#{fragment}\n"
    )


def test_documentation_policy_ignores_fenced_and_metadata_heading_targets(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        """---
# Metadata heading
link: "[Not a link](missing.md)"
---
# Topic

````markdown
## Fenced heading
[Not a link](missing.md)
```
## Still fenced
````not-a-closing-fence
## Also fenced
````

~~~markdown
## Tilde fenced
[Not a link](missing.md)
~~~

## Visible

[Valid](#visible)
[Metadata](#metadata-heading)
[Fenced](#fenced-heading)
[Short fence](#still-fenced)
[Trailing fence text](#also-fenced)
[Tilde](#tilde-fenced)
""",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "docs/01-topic.md:24: DOC203 Markdown heading fragment does not exist: #metadata-heading",
        "docs/01-topic.md:25: DOC203 Markdown heading fragment does not exist: #fenced-heading",
        "docs/01-topic.md:26: DOC203 Markdown heading fragment does not exist: #still-fenced",
        "docs/01-topic.md:27: DOC203 Markdown heading fragment does not exist: #also-fenced",
        "docs/01-topic.md:28: DOC203 Markdown heading fragment does not exist: #tilde-fenced",
    ]


def test_documentation_policy_keeps_archives_and_non_markdown_fragments_out_of_scope(
    tmp_path: Path,
) -> None:
    _write_minimal_documentation(tmp_path)
    _write(tmp_path / "paper/archive.md", "Archived prose without a document H1.\n\n## Evidence\n")
    _write(tmp_path / "research.md", "Archived prose [Unmaintained](missing.md)\n")
    _write(tmp_path / "source.py", "print('source')\n")
    _write(
        tmp_path / "docs/paper/archive.md", "Archived prose.\n\n## Evidence\n[Old](missing.md)\n"
    )
    _write(tmp_path / "docs/poster/archive.md", "Archived prose [Old](missing.md)\n")
    _write(
        tmp_path / "README.md",
        "# Readme\n\n[Archive evidence](paper/archive.md#evidence)\n"
        "[Archived manuscript](docs/paper/archive.md#evidence)\n"
        "[Source fragment](source.py#L999)\n"
        "[External](https://example.invalid/missing.md#absent)\n"
        "[Mail](mailto:nobody@example.invalid)\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_documentation_policy_reports_unreadable_linked_markdown_once(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    archive = tmp_path / "paper/archive.md"
    archive.parent.mkdir()
    archive.write_bytes(b"\xff")
    _write(
        tmp_path / "README.md",
        "# Readme\n\n[First](paper/archive.md#one)\n[Second](paper/archive.md#two)\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert len(result.stdout.splitlines()) == 1
    assert result.stdout.startswith("paper/archive.md:1: DOC002 cannot read document: ")


@pytest.mark.parametrize("target", ["#bad%escape", "#%FF", "docs%2F..%2F..%2Foutside.md#x"])
def test_documentation_policy_rejects_invalid_encoding_and_path_escape(
    tmp_path: Path, target: str
) -> None:
    _write_minimal_documentation(tmp_path)
    _write(tmp_path / "README.md", f"# Readme\n\n[Invalid]({target})\n")

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert result.stdout.startswith("README.md:3: DOC201 ")
    assert target in result.stdout


def test_documentation_policy_sorts_fragment_diagnostics_deterministically(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(tmp_path / "README.md", "# Readme\n\n[Z](#z)\n[A](#a)\n")
    _write(tmp_path / "DESIGN.md", "# Design\n\n[Missing](README.md#missing)\n")
    expected = (
        "DESIGN.md:3: DOC203 Markdown heading fragment does not exist: README.md#missing\n"
        "README.md:3: DOC203 Markdown heading fragment does not exist: #z\n"
        "README.md:4: DOC203 Markdown heading fragment does not exist: #a\n"
    )

    first = _run_policy("check_documentation.py", tmp_path)
    second = _run_policy("check_documentation.py", tmp_path)

    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout == expected


def test_documentation_policy_accepts_yaml_front_matter_before_h1(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        "---\ntitle: Topic metadata\n---\n\n# Topic\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_documentation_policy_accepts_stable_design_document_numbering_gaps(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/00-design-index.md",
        "# Design document index\n\n[Topic](01-topic.md)\n[Later topic](03-later-topic.md)\n",
    )
    _write(tmp_path / "docs/03-later-topic.md", "# Later topic\n")

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_documentation_policy_rejects_unclosed_yaml_front_matter(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        "---\ntitle: Topic metadata\n\n# Topic\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert "DOC105" in result.stdout


def test_documentation_policy_reports_structure_and_link_errors(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/01-topic.md",
        "# Topic\n\n### Jumped heading\n\n[Missing](missing.md)\n",
    )

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert "DOC103" in result.stdout
    assert "DOC202" in result.stdout


def test_documentation_policy_reports_index_and_adr_errors(tmp_path: Path) -> None:
    _write_minimal_documentation(tmp_path)
    _write(
        tmp_path / "docs/decisions/ADR-0001-example.md",
        """# ADR-0001: Example

**Status:** Accepted

## Decision

Decision.

## Consequences

Consequences.
""",
    )
    _write(tmp_path / "docs/00-design-index.md", "# Design document index\n")

    result = _run_policy("check_documentation.py", tmp_path)

    assert result.returncode == 1
    assert "DOC301" in result.stdout
    assert "DOC503" in result.stdout


def test_contract_naming_policy_accepts_explicit_semantics(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/gendertagger/models/contracts.py",
        """from datetime import datetime
from typing import Annotated, ClassVar
from uuid import UUID


class Contract:
    id: UUID
    project_id: Annotated[UUID | None, "identifier"]
    related_ids: Annotated[list[UUID] | None, "identifiers"]
    created_at: Annotated[datetime | None, "UTC"]
    timeout_seconds: float
    method_confidence: float
    descriptor: ClassVar[datetime]
""",
    )

    result = _run_policy("check_contract_naming.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_contract_naming_policy_reports_ambiguous_fields(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/gendertagger/models/contracts.py",
        """from datetime import datetime
from uuid import UUID


class Contract:
    confidence: float
    created: datetime
    project: UUID
    related: list[UUID]
    timeout: int
""",
    )

    result = _run_policy("check_contract_naming.py", tmp_path)

    assert result.returncode == 1
    assert [code for code in result.stdout.split() if code.startswith("GTN")] == [
        "GTN001",
        "GTN002",
        "GTN003",
        "GTN003",
        "GTN004",
    ]


def test_package_initializer_policy_accepts_docstring_only_packages(tmp_path: Path) -> None:
    _write(tmp_path / "src/gendertagger/__init__.py", '"""Package contract."""\n')
    _write(tmp_path / "src/gendertagger/domain/__init__.py", '"""Domain package."""\n')

    result = _run_policy("check_package_initializers.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_package_initializer_policy_requires_a_docstring(tmp_path: Path) -> None:
    _write(tmp_path / "src/gendertagger/__init__.py", "")

    result = _run_policy("check_package_initializers.py", tmp_path)

    assert result.returncode == 1
    assert "PKG101" in result.stdout


def test_package_initializer_policy_rejects_behavior_and_namespace_packages(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src/gendertagger/__init__.py",
        '"""Package contract."""\n\nfrom .domain.service import Service\n\nVERSION = "1"\n',
    )
    _write(tmp_path / "src/gendertagger/domain/service.py", "class Service: ...\n")

    result = _run_policy("check_package_initializers.py", tmp_path)

    assert result.returncode == 1
    assert [code for code in result.stdout.split() if code.startswith("PKG")] == [
        "PKG102",
        "PKG102",
        "PKG103",
    ]


def test_dead_code_policy_accepts_referenced_code_and_valid_protocols(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/gendertagger/services/protocol.py",
        """from typing import Protocol

class Greeter(Protocol):
    def greet(self, name: str) -> str:
        ...
""",
    )
    _write(
        tmp_path / "src/gendertagger/services/impl.py",
        """from .protocol import Greeter

class SimpleGreeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}"

def run() -> str:
    greeter: Greeter = SimpleGreeter()
    return greeter.greet("world")
""",
    )
    _write(
        tmp_path / "tests/test_run.py",
        """from gendertagger.services.impl import run

def test_run() -> None:
    assert run() == "Hello, world"
""",
    )

    result = _run_policy("check_dead_code.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_dead_code_policy_rejects_unreferenced_symbols(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/gendertagger/services/dead.py",
        """def dead_helper_function() -> None:
    pass
""",
    )

    result = _run_policy("check_dead_code.py", tmp_path)

    assert result.returncode == 1
    assert "DED001" in result.stdout


def test_dead_code_policy_rejects_protocol_not_implemented_error(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/gendertagger/services/protocol.py",
        """from typing import Protocol

class Compiler(Protocol):
    def compile(self) -> int:
        raise NotImplementedError
""",
    )
    _write(
        tmp_path / "src/gendertagger/services/usage.py",
        """from .protocol import Compiler

def use(c: Compiler) -> int:
    return c.compile()
""",
    )
    _write(
        tmp_path / "tests/test_use.py",
        """from gendertagger.services.usage import use
""",
    )

    result = _run_policy("check_dead_code.py", tmp_path)

    assert result.returncode == 1
    assert "DED002" in result.stdout
