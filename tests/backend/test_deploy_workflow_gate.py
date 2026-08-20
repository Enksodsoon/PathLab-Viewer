from pathlib import Path


def test_production_ci_gate_passes_sha_as_a_jq_argument() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert '--arg sha "${GITHUB_SHA}"' in workflow
    assert ".head_sha == $sha" in workflow
    assert "env.GITHUB_SHA" not in workflow


def test_production_ci_gate_keeps_the_jq_filter_on_one_quoted_line() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    jq_filter = (
        "[.check_runs[] | select(.name == $name and .head_sha == $sha)] "
        "| sort_by(.id) | last | .conclusion // empty"
    )

    assert f"'{jq_filter}'" in workflow
    assert f"'{jq_filter} \\" not in workflow


def test_production_workflow_rejects_missing_evidence_configuration_early() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    validation = workflow.index("Validate production deployment configuration")
    install_oci = workflow.index("Install OCI CLI")
    assert validation < install_oci
    assert '[[ "${#DEPLOY_EVIDENCE_KEY}" -ge 32 ]]' in workflow
    assert '[[ "${PROJECTED_EGRESS_BYTES}" =~ ^[0-9]+$ ]]' in workflow
    assert "PATHLAB_DEPLOY_EVIDENCE_KEY is missing or too short" in workflow
    assert "OCI_PROJECTED_MONTHLY_EGRESS_BYTES must be an integer" in workflow


def test_production_cost_query_uses_monthly_utc_day_boundaries() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert 'usage_start="$(date -u +%Y-%m-01T00:00:00Z)"' in workflow
    assert 'usage_end="$(date -u +%Y-%m-%dT00:00:00Z)"' in workflow
    assert 'usage_end="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' not in workflow
