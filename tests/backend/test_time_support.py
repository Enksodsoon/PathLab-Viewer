from datetime import UTC, datetime, timedelta, timezone

from wsi_viewer.time_support import as_utc, utc_now


def test_as_utc_attaches_utc_to_legacy_sqlite_timestamp() -> None:
    value = datetime(2026, 8, 22, 12, 30)

    assert as_utc(value) == datetime(2026, 8, 22, 12, 30, tzinfo=UTC)


def test_as_utc_converts_aware_timestamp() -> None:
    source_zone = timezone(timedelta(hours=7))
    value = datetime(2026, 8, 22, 19, 30, tzinfo=source_zone)

    assert as_utc(value) == datetime(2026, 8, 22, 12, 30, tzinfo=UTC)


def test_utc_now_is_aware_utc() -> None:
    current = utc_now()

    assert current.tzinfo is UTC
