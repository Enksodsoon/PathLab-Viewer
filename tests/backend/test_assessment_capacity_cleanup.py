import csv
import importlib.util
import io
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "assessment_capacity_cleanup", Path("scripts/assessment_capacity_cleanup.py")
)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


def exported(pairs):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_id", "item_id", "manual_feedback"])
    for identifier, item in pairs:
        writer.writerow([identifier, item, "Feedback with\na quoted newline"])
    return output.getvalue().encode()


def test_export_verifies_each_learner_item_instead_of_counting_lines():
    identifiers = {
        f"shard-{shard}-student-{seat}" for shard in range(1, 6) for seat in range(1, 101)
    }
    pairs = [
        (identifier, item)
        for identifier in identifiers
        for item in ("capacity-item-1", "capacity-static-dzi")
    ]
    assert cleanup.verify_fixture_export(exported(pairs), identifiers)
    assert not cleanup.verify_fixture_export(exported(pairs[:-1]), identifiers)
    assert not cleanup.verify_fixture_export(exported(pairs[:-1] + [pairs[0]]), identifiers)
    assert not cleanup.verify_fixture_export(exported(pairs), {"other-learner"})


@pytest.mark.parametrize(
    "raw", [b"", b"wrong,headers\na,b\n", b"\xff", b'student_id,item_id\n"unterminated']
)
def test_export_rejects_malformed_or_unrelated_content(raw):
    assert not cleanup.verify_fixture_export(raw, {"canary-student-1"})
