from __future__ import annotations

import shlex
from pathlib import Path
from typing import TypedDict, cast

import pytest
import yaml

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class _CiJob(TypedDict, total=False):
    extends: str
    stage: str
    script: list[str]
    variables: dict[str, str]
    artifacts: dict[str, object]
    rules: list[dict[str, str]]
    needs: list[dict[str, str | bool]]


@pytest.fixture(scope="module")
def image_jobs() -> dict[str, _CiJob]:
    pipeline = yaml.safe_load((_REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8"))
    # Only image jobs are selected; top-level stages and variables have different YAML shapes.
    return {
        name: cast(_CiJob, pipeline[name])
        for name in (
            ".kaniko_build",
            ".sbom",
            "backend_publish_image",
            "frontend_publish_image",
            "backend_sbom",
            "frontend_sbom",
        )
    }


def test_first_party_jobs_are_component_scoped_and_need_existing_jobs() -> None:
    pipeline = cast(
        dict[str, object],
        yaml.safe_load((_REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")),
    )
    # These keys intentionally override jobs supplied by GitLab security templates.
    jobs = {
        name: cast(_CiJob, definition)
        for name, definition in pipeline.items()
        if isinstance(definition, dict)
        and not name.startswith(".")
        and name not in {"sast", "secret_detection"}
        and ("stage" in definition or "extends" in definition)
    }

    assert jobs
    assert all(name.startswith(("backend_", "frontend_")) for name in jobs)

    for name, job in jobs.items():
        template = job.get("extends")
        if isinstance(template, str):
            assert template in pipeline, f"{name} extends missing template {template}"

        for dependency in job.get("needs", []):
            required_job = dependency.get("job")
            if isinstance(required_job, str):
                assert required_job in pipeline, f"{name} needs missing job {required_job}"


def test_publish_retains_branch_tag_and_adds_full_commit_tag(image_jobs: dict[str, _CiJob]) -> None:
    arguments = shlex.split(image_jobs[".kaniko_build"].get("script", [])[0])

    assert arguments[0] == "/kaniko/executor"
    destinations = [
        arguments[index + 1]
        for index, argument in enumerate(arguments)
        if argument == "--destination"
    ]
    assert sorted(destinations) == [
        "$CI_REGISTRY_IMAGE/$IMAGE_NAME:$CI_COMMIT_REF_SLUG",
        "$CI_REGISTRY_IMAGE/$IMAGE_NAME:$CI_COMMIT_SHA",
    ]
    assert arguments[arguments.index("--context") + 1] == "$CI_PROJECT_DIR/$IMAGE_CONTEXT"
    assert arguments[arguments.index("--dockerfile") + 1] == "$CI_PROJECT_DIR/$IMAGE_DOCKERFILE"


def test_publish_emits_one_digest_reference_for_sbom(image_jobs: dict[str, _CiJob]) -> None:
    publish = image_jobs[".kaniko_build"]
    scripts = publish.get("script", [])
    arguments = shlex.split(scripts[0])

    # Kaniko's image-name output repeats the reference for every destination tag.
    assert "--image-name-with-digest-file" not in arguments
    assert (
        arguments[arguments.index("--digest-file") + 1] == "$CI_PROJECT_DIR/$IMAGE_NAME-digest.txt"
    )
    assert shlex.split(scripts[1]) == [
        "printf",
        "%s@%s\\n",
        "$CI_REGISTRY_IMAGE/$IMAGE_NAME",
        "$(cat $CI_PROJECT_DIR/$IMAGE_NAME-digest.txt)",
        ">",
        "$CI_PROJECT_DIR/$IMAGE_NAME-image.txt",
    ]
    assert publish.get("artifacts", {}).get("paths") == ["$IMAGE_NAME-image.txt"]
    sbom = image_jobs[".sbom"]
    sbom_scripts = sbom.get("script", [])
    assert shlex.split(sbom_scripts[0]) == ["IMAGE_REF=$(cat $IMAGE_NAME-image.txt)"]
    assert shlex.split(sbom_scripts[1]) == [
        "syft",
        "registry:$IMAGE_REF",
        "-o",
        "spdx-json",
        ">",
        "$IMAGE_NAME-sbom.json",
    ]
    assert sbom.get("artifacts", {}).get("paths") == ["$IMAGE_NAME-sbom.json"]


@pytest.mark.parametrize("image_name", ["backend", "frontend"])
def test_each_image_inherits_publishing_and_its_own_sbom_artifact(
    image_jobs: dict[str, _CiJob], image_name: str
) -> None:
    publish_name = f"{image_name}_publish_image"
    publish = image_jobs[publish_name]
    sbom = image_jobs[f"{image_name}_sbom"]

    assert publish.get("extends") == ".kaniko_build"
    assert publish.get("variables") == {
        "IMAGE_NAME": image_name,
        "IMAGE_CONTEXT": image_name,
        "IMAGE_DOCKERFILE": f"deploy/docker/{image_name}.Dockerfile",
    }
    assert sbom.get("extends") == ".sbom"
    assert sbom.get("variables") == {"IMAGE_NAME": image_name}
    assert sbom.get("needs") == [{"job": publish_name, "artifacts": True}]
    for job in (publish, sbom):
        assert not {"script", "rules", "artifacts"}.intersection(job)


@pytest.mark.parametrize("template", [".kaniko_build", ".sbom"])
def test_publishing_and_sbom_remain_default_branch_only(
    image_jobs: dict[str, _CiJob], template: str
) -> None:
    assert image_jobs[template].get("rules") == [{"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"}]
