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
