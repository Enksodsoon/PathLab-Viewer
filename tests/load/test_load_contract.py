import os
import shutil
import subprocess
from pathlib import Path

import pytest

GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.is_file() else shutil.which("bash")


def test_k6_script_uses_manifest_profiles_and_seventy_thirty_mix() -> None:
    script = Path("tests/load/viewer.js").read_text(encoding="utf-8")

    assert "validateManifest" in script
    assert "MANIFEST_PATH" in script
    assert "PROFILE" in script
    assert "vus: 100" in script
    assert "duration: '10m'" in script
    assert "target: 300" in script
    assert "duration: '2m'" in script
    assert "duration: '10m', target: 300" in script
    assert "vus: 2" in script
    assert "duration: '30s'" in script
    assert "COMMON_REQUESTS = 7" in script
    assert "RANDOM_REQUESTS = 3" in script
    assert "__VU" in script
    assert "tileFailures" in script
    assert "tileLatency" in script
    assert "posterLatency" in script
    assert "http.batch" in script
    assert "let tileRoot" in script
    assert "if (!tileRoot)" in script
    assert "metadataBody = metadata.json()" in script
    assert "metadataBody.tileSource" in script
    assert "tileSource.replace" in script
    assert "`${base}/tiles/${slide.publicId}/${path}`" not in script
    assert "tileFailures.add(true)" in script
    assert "sleep(1)" in script


def test_load_wrapper_requires_inputs_and_never_discovers_slide_ids() -> None:
    script = Path("deploy/scripts/run-viewer-load-test.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert 'BASE_URL:?BASE_URL is required' in script
    assert 'MANIFEST_PATH:?MANIFEST_PATH is required' in script
    assert '[[ "${MANIFEST_PATH}" = /* ]]' in script
    assert "command -v k6" in script
    assert "smoke|acceptance|capacity300" in script
    assert "public_id" not in script.lower()
    assert "curl" not in script


def test_capacity_runner_uses_all_three_profiles_and_strict_safety_monitoring() -> None:
    script = Path("deploy/scripts/run-capacity-certification.sh").read_text(
        encoding="utf-8"
    )

    assert "run_profile smoke 50 false" in script
    assert "run_profile acceptance 630 false" in script
    assert "run_profile capacity300 900 true" in script
    assert "/v1/status" in script
    assert '["data"]["attributes"]["vus"] >= 300' in script
    assert "certification_watchdog.py" in script
    assert "certification_report.py" in script
    assert "generate_remote_manifest.py" in script
    assert "generate_synthetic_ome.py" in script
    assert "capacity-fixture.spec.ts" in script
    assert "CAPACITY_FIXTURE_ACTION=prepare" in script
    assert "CAPACITY_FIXTURE_ACTION=cleanup" in script
    assert "CAPACITY_FIXTURE_PREPARE_DIAGNOSTIC" in script
    assert "CAPACITY_FIXTURE_CLEANUP_DIAGNOSTIC" in script
    assert (
        '"${CAPACITY_EVIDENCE_DIR}/capacity-fixture-prepare-diagnostic.json"'
        in script
    )
    assert "Synthetic fixture preparation failed at stage:" in script
    assert "fixture_prepare_status=$?" in script
    assert 'if [[ "${fixture_prepare_status}" -ne 0 ]]' in script
    assert "Capacity phase: synthetic fixture generation." in script
    assert "Capacity certification failed during synthetic fixture generation." in script
    assert "Capacity phase: synthetic fixture preparation." in script
    assert "Capacity phase: 100-user acceptance profile." in script
    assert "Capacity phase: 300-user capacity profile." in script
    assert "--width 4096" in script
    assert "--height 4096" in script
    assert "playwright.live.config.ts" in script


def test_live_capacity_specs_wait_for_current_admin_sign_in() -> None:
    helper = Path(
        "apps/web/e2e-live/capacity-helpers.ts"
    ).read_text(encoding="utf-8")

    assert "await expect(heading).toBeVisible" in helper
    assert "name: 'Enter workspace'" in helper
    assert "name: 'Sign in'" not in helper
    assert "getByLabel('Username', { exact: true })" in helper
    assert "getByLabel('Password', { exact: true })" in helper
    assert "authenticationResponse.ok()" in helper
    for path in (
        "apps/web/e2e-live/capacity-fixture.spec.ts",
        "apps/web/e2e-live/capacity-certification.spec.ts",
    ):
        assert "signIn(page, username, password)" in Path(path).read_text(
            encoding="utf-8"
        )


def test_live_capacity_specs_share_scoped_upload_and_current_api_contracts() -> None:
    fixture = Path(
        "apps/web/e2e-live/capacity-fixture.spec.ts"
    ).read_text(encoding="utf-8")
    certification = Path(
        "apps/web/e2e-live/capacity-certification.spec.ts"
    ).read_text(encoding="utf-8")

    assert "uploadSyntheticSlide" in fixture
    assert "uploadSyntheticSlide" in certification
    assert "deidentifiedConfirmed: true" in fixture
    assert "/api/v2/admin/slides/" in certification
    assert "waitForSlideDeletion" in fixture
    assert "waitForSlideDeletion" in certification
    assert "waitForSlideConversion" in fixture
    assert "CONVERSION_TIMEOUT" in Path(
        "apps/web/e2e-live/capacity-helpers.ts"
    ).read_text(encoding="utf-8")


def test_capacity_diagnostics_separate_prepare_and_cleanup_failures() -> None:
    fixture = Path(
        "apps/web/e2e-live/capacity-fixture.spec.ts"
    ).read_text(encoding="utf-8")
    runner = Path("deploy/scripts/run-capacity-certification.sh").read_text(
        encoding="utf-8"
    )
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(
        encoding="utf-8"
    )

    for name in (
        "CAPACITY_FIXTURE_PREPARE_DIAGNOSTIC",
        "CAPACITY_FIXTURE_CLEANUP_DIAGNOSTIC",
    ):
        assert name in fixture
        assert name in runner
    assert "httpStatus" in fixture
    assert "errorCode" in fixture
    assert "prepare-diagnostic.json" in workflow
    assert "cleanup-diagnostic.json" in workflow


def test_arm64_container_job_has_a_bounded_timeout() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    containers = workflow.split("  containers:", maxsplit=1)[1]

    assert "timeout-minutes: 30" in containers


def test_capacity_workflow_does_not_require_preexisting_slide_secrets() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(
        encoding="utf-8"
    )

    assert "run: bash deploy/scripts/run-capacity-certification.sh" in workflow
    assert "id: capacity-runner" in workflow
    assert "continue-on-error: true" in workflow
    assert "steps.capacity-runner.outcome == 'failure'" in workflow
    assert "Capacity certification failed at sanitized fixture stage:" in workflow
    assert "LOAD_TEST_PUBLIC_ID: ${{ secrets." not in workflow
    assert "LOAD_TEST_ADMIN_SLIDE_ID: ${{ secrets." not in workflow
    assert "LOAD_TEST_ADMIN_USERNAME" in workflow
    assert "LOAD_TEST_ADMIN_PASSWORD" in workflow


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_load_wrapper_rejects_missing_inputs() -> None:
    environment = os.environ.copy()
    environment.pop("BASE_URL", None)
    environment.pop("MANIFEST_PATH", None)

    result = subprocess.run(
        [str(BASH), "deploy/scripts/run-viewer-load-test.sh", "smoke"],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "BASE_URL is required" in result.stderr
