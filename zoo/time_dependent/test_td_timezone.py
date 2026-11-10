from datetime import datetime, timezone


def test_report_hour_matches_utc():
    # Passes on a machine set to UTC (most CI servers), fails on a laptop in
    # almost any other time zone.
    assert datetime.now().hour == datetime.now(timezone.utc).hour
