from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.validate_security_baseline import (
    evaluate_findings,
    reconcile_egress,
    reconcile_routes,
    validate,
)


def finding(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "SEC-TEST-1",
        "severity": "High",
        "reachable": True,
        "status": "OPEN",
        "owner": "Platform Security Owner",
        "ownerTasks": ["P7-G01"],
    }
    value.update(overrides)
    return value


def test_current_security_baseline_reconciles() -> None:
    result = validate()
    assert result == {
        "backendRoutes": 167,
        "frontendRoutes": 14,
        "egressFiles": 61,
        "findingResult": "SUCCESS",
    }


def test_seeded_unknown_route_is_rejected() -> None:
    with pytest.raises(ValueError, match="backend route is unmapped"):
        reconcile_routes(
            ["GET|/seeded/undeclared|server/wsi_viewer/seeded.py|seeded"],
            [{"kind": "prefix", "value": "/api/"}],
        )


def test_seeded_undeclared_egress_is_rejected() -> None:
    with pytest.raises(ValueError, match="egress-bearing file must map exactly once"):
        reconcile_egress(
            ["seeded/undeclared-client.py"],
            [{"glob": "scripts/*"}],
            require_used_rules=False,
        )


def test_reachable_unresolved_critical_is_negative() -> None:
    result = evaluate_findings(
        [finding(severity="Critical", status="OPEN")], "2026-09-03T00:00:00Z"
    )
    assert result == "NEGATIVE"


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"status": "MITIGATED", "mitigationVerified": False, "expiresAt": "2026-09-10T00:00:00Z"},
        {"status": "MITIGATED", "mitigationVerified": True},
        {"status": "MITIGATED", "mitigationVerified": True, "expiresAt": "2026-10-04T00:00:01Z"},
    ],
)
def test_unacceptable_high_is_negative(overrides: dict[str, object]) -> None:
    assert evaluate_findings([finding(**overrides)], "2026-09-03T00:00:00Z") == "NEGATIVE"


def test_verified_high_mitigation_within_thirty_days_is_accepted() -> None:
    assessed = datetime(2026, 9, 3, tzinfo=UTC)
    result = evaluate_findings(
        [
            finding(
                status="MITIGATED",
                mitigationVerified=True,
                expiresAt=(assessed + timedelta(days=30)).isoformat(),
            )
        ],
        assessed.isoformat(),
    )
    assert result == "SUCCESS"


def test_finding_without_owner_is_rejected() -> None:
    with pytest.raises(ValueError, match="finding lacks owner/task"):
        evaluate_findings([finding(owner="")], "2026-09-03T00:00:00Z")
