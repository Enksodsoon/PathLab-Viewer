import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_certification_tools import healthy_evidence_context

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
    assert "TARGET_VUS" in script
    assert "TARGET_DURATION" in script
    assert "TARGET_RAMP_DURATION" in script
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


def test_classroom_harness_consumes_realtime_and_tile_work_concurrently() -> None:
    script = Path("tests/load/classroom_sse.py").read_text(encoding="utf-8")

    assert "aiter_lines" in script
    assert "publish_presenter" in script
    assert "request_tiles" in script
    assert "exercise_discrete_events" in script
    assert "reconnect_delay" in script
    assert "presenterLatencyMs" in script
    assert "finalConvergence" in script
    assert "presenterPersistenceWritesPerSecond" in script
    assert "PATHLAB_CLASSROOM_EXPECT_RESTART" in script
    assert 'get_with_retry(admin, "/api/v1/admin/classroom/metrics")' in script
    assert 'report["distinctHubEpochs"] < 2' in script
    assert "restricted to local ephemeral targets" in script
    assert "ALLOW_PRODUCTION" not in script


def test_load_wrapper_requires_inputs_and_never_discovers_slide_ids() -> None:
    script = Path("deploy/scripts/run-viewer-load-test.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "BASE_URL:?BASE_URL is required" in script
    assert "MANIFEST_PATH:?MANIFEST_PATH is required" in script
    assert '[[ "${MANIFEST_PATH}" = /* ]]' in script
    assert "command -v k6" in script
    assert "smoke|staged|acceptance|capacity300" in script
    assert "public_id" not in script.lower()
    assert "curl" not in script


def test_capacity_runner_uses_all_three_profiles_and_strict_safety_monitoring() -> None:
    script = Path("deploy/scripts/run-capacity-certification.sh").read_text(encoding="utf-8")

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
    assert '"${CAPACITY_EVIDENCE_DIR}/capacity-fixture-prepare-diagnostic.json"' in script
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


def test_capacity_runner_verifies_the_deployed_sha_before_creating_fixtures() -> None:
    script = Path("deploy/scripts/run-capacity-certification.sh").read_text(encoding="utf-8")

    verification = script.index("Capacity phase: exact deployed release verification.")
    fixture_generation = script.index("Capacity phase: synthetic fixture generation.")
    assert verification < fixture_generation
    assert 'first.get("releaseSha") == sys.argv[2]' in script


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_capacity_runner_fails_before_any_live_work_without_valid_v2_context(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "CAPACITY_BASE_URL": "https://capacity.example.test",
            "LOAD_TEST_ADMIN_USERNAME": "synthetic-admin",
            "LOAD_TEST_ADMIN_PASSWORD": "masked-password",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123456",
            "CAPACITY_BROWSER_CI_RUN_ID": "987654",
            "CAPACITY_DISTRIBUTED_ORCHESTRATOR_READY": "true",
            "CAPACITY_EVIDENCE_DIR": str(tmp_path / "evidence"),
        }
    )
    environment.pop("CAPACITY_EVIDENCE_CONTEXT", None)

    result = subprocess.run(
        [str(BASH), "deploy/scripts/run-capacity-certification.sh"],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "CAPACITY_EVIDENCE_CONTEXT" in result.stderr
    assert "Capacity phase:" not in result.stdout


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
@pytest.mark.parametrize("orchestrator_ready", [None, "false"])
def test_capacity_runner_refuses_valid_context_until_distributed_orchestrator_is_ready(
    tmp_path: Path, orchestrator_ready: str | None
) -> None:
    context_path = tmp_path / "capacity-evidence-context-v2.json"
    context_path.write_text(json.dumps(healthy_evidence_context()), encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "CAPACITY_BASE_URL": "https://capacity.example.test",
            "LOAD_TEST_ADMIN_USERNAME": "synthetic-admin",
            "LOAD_TEST_ADMIN_PASSWORD": "masked-password",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123456",
            "CAPACITY_BROWSER_CI_RUN_ID": "123456",
            "CAPACITY_EVIDENCE_DIR": str(tmp_path / "evidence"),
            "CAPACITY_EVIDENCE_CONTEXT": str(context_path),
        }
    )
    if orchestrator_ready is None:
        environment.pop("CAPACITY_DISTRIBUTED_ORCHESTRATOR_READY", None)
    else:
        environment["CAPACITY_DISTRIBUTED_ORCHESTRATOR_READY"] = orchestrator_ready

    result = subprocess.run(
        [str(BASH), "deploy/scripts/run-capacity-certification.sh"],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "Distributed capacity orchestrator is not ready; live load is disabled until Task 6."
        in result.stderr
    )
    assert "k6 is required" not in result.stderr
    assert "Capacity phase:" not in result.stdout


def test_protected_capacity_workflow_uses_six_evidence_preserving_distributed_shards() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(encoding="utf-8")

    assert "distributed_shard.py" in workflow
    assert "shard-index: [0, 1, 2, 3, 4, 5]" in workflow
    assert "fail-fast: false" in workflow


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
@pytest.mark.parametrize(
    ("configured", "expected_status", "expected_services"),
    [
        (
            "api\ncaddy\ntile-service\ntusd\nworker",
            1,
            "",
        ),
        (
            "api\ncaddy\nclassroom\ntile-service\ntusd\nworker",
            0,
            "api\ncaddy\nclassroom\ntile-service\ntusd\nworker",
        ),
        ("api\ncaddy\ntusd\nworker", 1, ""),
        ("api\ncaddy\nmetrics\ntile-service\ntusd\nworker", 1, ""),
    ],
)
def test_load_observer_accepts_only_the_exact_environment_topologies(
    configured: str, expected_status: int, expected_services: str
) -> None:
    environment = os.environ.copy()
    environment["PATHLAB_TEST_CONFIGURED_SERVICES"] = configured
    result = subprocess.run(
        [
            str(BASH),
            "-c",
            (
                "PATHLAB_OBSERVER_LIBRARY=1 source deploy/scripts/observe-load.sh; "
                'pathlab_expected_services "$PATHLAB_TEST_CONFIGURED_SERVICES"'
            ),
            "observer-contract",
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == expected_status
    assert result.stdout.strip() == expected_services


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_observer_call_chain_is_valid_when_checkout_drops_executable_mode() -> None:
    runner = Path("deploy/scripts/run-capacity-certification.sh").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert 'bash deploy/scripts/observe-via-bastion.sh "${observe_duration}"' in runner
    assert 'exec bash "${LIVE_DIR}/deploy/scripts/observe-load.sh"' in release
    for script in (
        "deploy/scripts/run-capacity-certification.sh",
        "deploy/scripts/deploy-release.sh",
        "deploy/scripts/observe-via-bastion.sh",
        "deploy/scripts/observe-load.sh",
    ):
        result = subprocess.run(
            [str(BASH), "-n", script], check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_live_capacity_specs_wait_for_current_admin_sign_in() -> None:
    helper = Path("apps/web/e2e-live/capacity-helpers.ts").read_text(encoding="utf-8")

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
        assert "signIn(page, username, password)" in Path(path).read_text(encoding="utf-8")


def test_live_capacity_specs_share_scoped_upload_and_current_api_contracts() -> None:
    fixture = Path("apps/web/e2e-live/capacity-fixture.spec.ts").read_text(encoding="utf-8")
    certification = Path("apps/web/e2e-live/capacity-certification.spec.ts").read_text(
        encoding="utf-8"
    )

    assert "uploadSyntheticSlide" in fixture
    assert "uploadSyntheticSlide" in certification
    assert "deidentifiedConfirmed: true" in fixture
    assert "/api/v2/admin/slides/" in certification
    assert "waitForSlideDeletion" in fixture
    assert "waitForSlideDeletion" in certification
    assert "waitForSlideConversion" in fixture
    assert "CONVERSION_TIMEOUT" in Path("apps/web/e2e-live/capacity-helpers.ts").read_text(
        encoding="utf-8"
    )


def test_capacity_diagnostics_separate_prepare_and_cleanup_failures() -> None:
    fixture = Path("apps/web/e2e-live/capacity-fixture.spec.ts").read_text(encoding="utf-8")
    runner = Path("deploy/scripts/run-capacity-certification.sh").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(encoding="utf-8")

    for name in (
        "CAPACITY_FIXTURE_PREPARE_DIAGNOSTIC",
        "CAPACITY_FIXTURE_CLEANUP_DIAGNOSTIC",
    ):
        assert name in fixture
        assert name in runner
    assert "httpStatus" in fixture
    assert "errorCode" in fixture
    assert "capacity-sentinel.json" in workflow
    assert "cleanup-capacity-certification.sh" in workflow
    assert "if: always()" in workflow
    assert "prepare-diagnostic.json" not in workflow
    assert "cleanup-diagnostic.json" not in workflow


def test_arm64_container_job_has_a_bounded_timeout() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    containers = workflow.split("  containers:", maxsplit=1)[1]

    assert "timeout-minutes: 30" in containers


def test_capacity_workflow_requires_only_dedicated_synthetic_sentinel_ids() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(encoding="utf-8")

    assert "run-capacity-sentinels.sh" in workflow
    assert "CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON" in workflow
    assert "LOAD_TEST_PUBLIC_ID: ${{ secrets." in workflow
    assert "LOAD_TEST_ADMIN_SLIDE_ID: ${{ secrets." in workflow
    assert "LOAD_TEST_ADMIN_USERNAME" in workflow
    assert "LOAD_TEST_ADMIN_PASSWORD" in workflow


def test_capacity_workflow_requires_current_browser_ci() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(encoding="utf-8")

    required_checks = workflow.split("for check in backend", maxsplit=1)[1].split("do", maxsplit=1)[
        0
    ]
    assert "browser" in required_checks.split()
    assert "filter=latest" in workflow
    assert "CAPACITY_BROWSER_CI_RUN_ID" in workflow


def test_public_capacity_load_is_manual_bounded_and_public_only() -> None:
    workflow = Path(".github/workflows/public-capacity-load.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "RUN_PUBLIC_300" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "group: production-control" in workflow
    assert "name: production" in workflow
    assert "timeout-minutes: 25" in workflow
    assert "LOAD_TEST_PUBLIC_ID: ${{ secrets.LOAD_TEST_PUBLIC_ID }}" in workflow
    assert "LOAD_TEST_ADMIN_" not in workflow
    assert "PROFILE=capacity300" in workflow
    assert "consecutive_failures >= 2" in workflow
    assert "public-capacity-manifest.json" in workflow
    assert "path: ${{ env.EVIDENCE_DIR }}" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "schedule:" not in workflow


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
