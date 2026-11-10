from brittle_settings import get


def test_locale_is_canadian():
    # Brittle: passes only because the setter test happened to run first.
    assert get("locale") == "en_CA"
