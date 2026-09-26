from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex
from wsi_viewer.models import StudyCourse


def test_study_live_index_predicate_matches_across_dialects() -> None:
    index = next(
        index
        for index in StudyCourse.__table__.indexes
        if index.name == "uq_study_courses_one_live"
    )
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        compiled = str(CreateIndex(index).compile(dialect=dialect))
        assert "ON study_courses (status) WHERE status IN ('preparation', 'active')" in compiled
