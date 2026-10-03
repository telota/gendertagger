from __future__ import annotations

import shlex
from pathlib import Path
from typing import TypedDict, cast

import pytest
import yaml

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_SUITES = {
    "backend_core_test": "core",
    "backend_postgres_test": "postgres",
    "backend_celery_test": "redis",
}
_SCIENTIFIC_COVERAGE_MODULES = {
    "src/gendertagger/methods/normalization.py",
    "src/gendertagger/domain/aggregation.py",
    "src/gendertagger/domain/aggregation_assessment.py",
    "src/gendertagger/export/tei_profile.py",
}


class _CiJob(TypedDict, total=False):
    extends: str
    image: str
    stage: str
    before_script: list[str]
    script: list[str]
    variables: dict[str, str]
    artifacts: dict[str, object]
    needs: list[dict[str, str | bool]]
    cache: dict[str, object] | list[object]


@pytest.fixture(scope="module")
def verification_pipeline() -> dict[str, object]:
    return cast(
        dict[str, object],
        yaml.safe_load((_REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")),
    )


@pytest.fixture(scope="module")
def verification_jobs(verification_pipeline: dict[str, object]) -> dict[str, _CiJob]:
    return {
        name: cast(_CiJob, definition)
        for name, definition in verification_pipeline.items()
        if isinstance(definition, dict)
        and name.startswith(("backend_", "frontend_", ".backend_", ".frontend_"))
    }


@pytest.mark.parametrize(
    ("template_name", "cache_policy", "paths", "files", "tool_prefix"),
    [
        (
            ".backend_uv_job",
            "UV_CACHE_POLICY",
            [".uv-cache/"],
            ["backend/uv.lock", "backend/pyproject.toml"],
            "uv-0.12.5",
        ),
        (
            ".frontend_node_job",
            "NPM_CACHE_POLICY",
            ["frontend/.npm/"],
            ["frontend/package-lock.json", "frontend/package.json"],
            "npm",
        ),
    ],
)
def test_dependency_caches_reuse_downloads_without_reusing_installed_environments(
    verification_pipeline: dict[str, object],
    verification_jobs: dict[str, _CiJob],
    template_name: str,
    cache_policy: str,
    paths: list[str],
    files: list[str],
    tool_prefix: str,
) -> None:
    template = verification_jobs[template_name]
    cache = template.get("cache")
    assert isinstance(cache, dict)
    assert cache["paths"] == paths
    assert cache["policy"] == f"${cache_policy}"
    key = cast(dict[str, object], cache["key"])
    assert key["files"] == files
    image, digest = template.get("image", "").split("@sha256:")
    assert key["prefix"] == f"{tool_prefix}-{image.replace(':', '-')}-{digest[:12]}-linux"
    assert "/" not in str(key["prefix"])
    if cache_policy == "UV_CACHE_POLICY":
        uv_pins = {
            argument
            for job in verification_jobs.values()
            for command in job.get("before_script", [])
            for argument in shlex.split(command)
            if argument.startswith("uv==")
        }
        assert uv_pins == {tool_prefix.replace("uv-", "uv==", 1)}
    variables = cast(dict[str, str], verification_pipeline["variables"])
    assert variables[cache_policy] == "pull"
    defaults = cast(dict[str, object], verification_pipeline["default"])
    assert "cache" not in defaults


@pytest.mark.parametrize(
    ("cache_policy", "writer"),
    [("UV_CACHE_POLICY", "backend_quality"), ("NPM_CACHE_POLICY", "frontend_quality")],
)
def test_parallel_cache_consumers_have_one_declared_writer(
    verification_jobs: dict[str, _CiJob], cache_policy: str, writer: str
) -> None:
    writers = {
        name
        for name, job in verification_jobs.items()
        if job.get("variables", {}).get(cache_policy) == "pull-push"
    }
    assert writers == {writer}
    for name, job in verification_jobs.items():
        if name in {".backend_uv_job", ".frontend_node_job"}:
            continue
        assert "cache" not in job or name == "backend_repository_policy"
    assert verification_jobs["backend_repository_policy"].get("cache") == []


@pytest.mark.parametrize(
    ("job_name", "prerequisites"),
    [
        ("frontend_test", ["frontend_quality", "frontend_dependency_audit"]),
        ("frontend_build", ["frontend_test"]),
        ("backend_build", ["backend_lockfile", "backend_repository_policy"]),
    ],
)
def test_component_dependencies_avoid_unrelated_gate_and_artifact_downloads(
    verification_jobs: dict[str, _CiJob], job_name: str, prerequisites: list[str]
) -> None:
    job = verification_jobs[job_name]
    assert job.get("needs") == [{"job": name, "artifacts": False} for name in prerequisites]
    assert "dependencies" not in job
    assert "rules" not in job
    assert "allow_failure" not in job


def test_image_publication_keeps_the_barrier_across_all_verification_stages(
    verification_pipeline: dict[str, object], verification_jobs: dict[str, _CiJob]
) -> None:
    publish_template = cast(_CiJob, verification_pipeline[".kaniko_build"])
    stages = cast(list[str], verification_pipeline["stages"])
    assert publish_template.get("stage") == "publish"
    assert stages.index("publish") > max(
        stages.index(stage)
        for stage in ("validate", "test", "coverage", "package", "secret-detection")
    )
    assert "needs" not in publish_template
    for name in ("backend_publish_image", "frontend_publish_image"):
        job = verification_jobs[name]
        assert job.get("extends") == ".kaniko_build"
        assert "needs" not in job
    for name in _BACKEND_SUITES:
        assert "needs" not in verification_jobs[name]


def test_standard_library_checks_and_build_do_not_install_runtime_dependencies(
    verification_jobs: dict[str, _CiJob],
) -> None:
    lightweight_template = verification_jobs[".backend_uv_job"]
    setup = lightweight_template.get("before_script", [])
    assert setup
    assert all("sync" not in script for script in setup)
    for name in ("backend_repository_policy", "backend_build"):
        job = verification_jobs[name]
        assert job.get("extends") == ".backend_uv_job"
        assert "before_script" not in job
        assert all(
            "uv run" not in script and "uv sync" not in script for script in job.get("script", [])
        )

    assert verification_jobs["backend_repository_policy"].get("script") == [
        "python scripts/check_documentation.py",
        "python scripts/check_contract_naming.py",
        "python scripts/check_package_initializers.py",
        "python scripts/check_dead_code.py",
    ]
    assert verification_jobs["backend_build"].get("script") == [
        "uv build --no-sources",
        "python scripts/check_distribution.py dist/*",
    ]


@pytest.mark.parametrize("job_name", ["backend_quality", "backend_pyright", *_BACKEND_SUITES])
def test_typing_and_runtime_suites_keep_the_complete_locked_environment(
    verification_jobs: dict[str, _CiJob], job_name: str
) -> None:
    job = verification_jobs[job_name]
    assert job.get("extends") == ".backend_python_job"
    setup = job.get(
        "before_script", verification_jobs[".backend_python_job"].get("before_script", [])
    )
    assert "uv sync --locked" in setup


@pytest.mark.parametrize(("job_name", "profile"), _BACKEND_SUITES.items())
def test_backend_suites_use_canonical_covered_profiles_and_publish_case_timings(
    verification_jobs: dict[str, _CiJob], job_name: str, profile: str
) -> None:
    job = verification_jobs[job_name]
    arguments = shlex.split(job.get("script", [])[-1])
    assert arguments[:3] == ["timeout", "--signal=TERM", "--kill-after=30s"]
    assert arguments[3] == ("15m" if profile == "core" else "20m")
    assert arguments[4:] == [
        "uv",
        "run",
        "--locked",
        "python",
        "scripts/run_tests.py",
        profile,
        "--coverage",
        "--junitxml",
        f"junit-{profile}.xml",
    ]
    assert job.get("variables", {}).get("COVERAGE_FILE") == f".coverage.{profile}"
    artifacts = job.get("artifacts", {})
    assert artifacts["when"] == "always"
    assert artifacts["paths"] == [
        f"backend/.coverage.{profile}",
        f"backend/coverage-{profile}.xml",
        f"backend/junit-{profile}.xml",
    ]
    assert artifacts["reports"] == {"junit": f"backend/junit-{profile}.xml"}


def test_combined_coverage_requires_all_suites_and_preserves_scientific_floors(
    verification_jobs: dict[str, _CiJob],
) -> None:
    job = verification_jobs["backend_coverage"]
    assert job.get("extends") == ".backend_uv_job"
    assert job.get("needs") == [{"job": name, "artifacts": True} for name in _BACKEND_SUITES]
    scripts = job.get("script", [])
    assert scripts[0] == "uv sync --locked --only-group test --no-install-project"
    commands = [shlex.split(script) for script in scripts[1:]]
    assert all(
        command[:5] == ["uv", "run", "--locked", "--no-sync", "coverage"] for command in commands
    )
    assert commands[0][5:] == ["combine", ".coverage.core", ".coverage.postgres", ".coverage.redis"]
    reports = [command[5:] for command in commands if command[5] == "report"]
    assert reports[0] == ["report", "--fail-under=85"]
    assert {tuple(report) for report in reports[1:]} == {
        ("report", f"--include={module}", "--fail-under=100")
        for module in _SCIENTIFIC_COVERAGE_MODULES
    }


def test_frontend_ci_keeps_coverage_and_publishes_case_timings(
    verification_jobs: dict[str, _CiJob],
) -> None:
    job = verification_jobs["frontend_test"]
    assert shlex.split(job.get("script", [])[0]) == [
        "npm",
        "run",
        "test:coverage",
        "--",
        "--reporter=default",
        "--reporter=junit",
        "--outputFile.junit=junit-frontend.xml",
    ]
    reports = cast(dict[str, object], job.get("artifacts", {})["reports"])
    assert reports["junit"] == "frontend/junit-frontend.xml"
    assert reports["coverage_report"] == {
        "coverage_format": "cobertura",
        "path": "frontend/coverage/cobertura-coverage.xml",
    }


@pytest.mark.parametrize("job_name", [*_BACKEND_SUITES, "backend_coverage", "frontend_test"])
def test_runtime_and_coverage_gates_remain_unconditional_and_blocking(
    verification_jobs: dict[str, _CiJob], job_name: str
) -> None:
    job = verification_jobs[job_name]
    assert "rules" not in job
    assert "allow_failure" not in job


def test_push_hook_preserves_all_filenames_as_data_in_one_invocation() -> None:
    configuration = cast(
        dict[str, object],
        yaml.safe_load((_REPOSITORY_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")),
    )
    repositories = cast(list[dict[str, object]], configuration["repos"])
    hooks = cast(list[dict[str, object]], repositories[0]["hooks"])
    hook = next(item for item in hooks if item.get("id") == "affected-verification")

    assert shlex.split(str(hook["entry"]))[-1] == "--"
    assert hook.get("pass_filenames") is True
    assert hook.get("require_serial") is True
