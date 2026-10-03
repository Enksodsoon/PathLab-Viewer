"""Score precision probes use temporary tables and the actual ORM column types."""

import os
from decimal import Decimal

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, select
from sqlalchemy.exc import DataError
from test_assessment_contract_v2 import v2_document
from wsi_viewer.assessment_contract import AssessmentContractError, score_item
from wsi_viewer.assessment_contract_v2 import compile_assessment_v2, flatten_v2_items
from wsi_viewer.models import AssessmentScoreVersion


@pytest.fixture
def postgres_score_probe():
    url = os.getenv("PATHLAB_POSTGRES_TEST_URL")
    if not url:
        pytest.skip("isolated PostgreSQL required for actual score precision")
    engine = create_engine(url)
    columns = AssessmentScoreVersion.__table__.c
    probe = Table(
        "assessment_score_boundary_probe",
        MetaData(),
        Column("points", columns.points.type, nullable=False),
        Column("maximum_points", columns.maximum_points.type, nullable=False),
        prefixes=["TEMPORARY"],
    )
    try:
        with engine.connect() as connection, connection.begin():
            probe.create(connection)
            yield connection, probe
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("points", "expected"), [("999999999.999", "999999999.999"), ("1.0055", "1.006")]
)
def test_postgres_preserves_compiled_assessment_boundary_and_rounding(
    postgres_score_probe, points: str, expected: str
) -> None:
    connection, probe = postgres_score_probe
    document = v2_document()
    document["sections"][0]["items"][0]["points"] = points  # type: ignore[index]
    compiled = compile_assessment_v2(document)
    item = flatten_v2_items(compiled.definition)[0]
    earned = score_item(item, {"optionId": "option-lepidic"})
    connection.execute(probe.insert().values(points=earned, maximum_points=Decimal(points)))
    stored = connection.execute(select(probe)).one()
    assert stored.points == Decimal(expected)
    assert stored.maximum_points == Decimal(expected)


@pytest.mark.parametrize("points", ["1000000000", "999999999.9995"])
def test_postgres_overflow_is_rejected_before_assessment_publication(
    postgres_score_probe, points: str
) -> None:
    connection, probe = postgres_score_probe
    with pytest.raises(DataError) as overflow, connection.begin_nested():
        connection.execute(
            probe.insert().values(points=Decimal(points), maximum_points=Decimal(points))
        )
    assert overflow.value.orig.sqlstate == "22003"
    document = v2_document()
    document["sections"][0]["items"][0]["points"] = points  # type: ignore[index]
    with pytest.raises(AssessmentContractError, match="ASSESSMENT_POINTS_INVALID"):
        compile_assessment_v2(document)
