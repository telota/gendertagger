from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast
from uuid import uuid4

import pytest
from tests.seeding import CompletedRun

from gendertagger.models.aggregation import AggregationResultWrite
from gendertagger.models.classification import AgreementTier, CertaintyTier


class _SeedModule(Protocol):
    def main(self, argv: list[str]) -> int: ...

    def _tier_results(self, completed: CompletedRun) -> list[AggregationResultWrite]: ...


def _load_seed_module() -> _SeedModule:
    script = Path(__file__).resolve().parents[2] / "scripts/seed_frontend_development.py"
    spec = spec_from_file_location("seed_frontend_development", script)
    if spec is None or spec.loader is None:
        msg = f"could not load {script}"
        raise RuntimeError(msg)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_SeedModule, module)


seed = _load_seed_module()


def test_parser_requires_explicit_development_database_confirmation() -> None:
    with pytest.raises(SystemExit, match="2"):
        seed.main([])


def test_tier_results_cover_every_canonical_tier() -> None:
    people = {f"demo-{index}": SimpleNamespace(id=uuid4()) for index in range(1, 8)}
    completed = CompletedRun(run=None, execution_ids=(), people=people)  # type: ignore[arg-type]

    results = seed._tier_results(completed)

    agreement_tiers = {item.result.agreement_tier for item in results}
    certainty_tiers = {item.result.certainty_tier for item in results}
    assert agreement_tiers == set(AgreementTier)
    assert certainty_tiers == set(CertaintyTier)
    assert sum(bool(item.has_prediction_error) for item in results) == 1
