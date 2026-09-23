from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
        "PLAN.md",
        "SPEC.md",
        "AGENTS.md",
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
