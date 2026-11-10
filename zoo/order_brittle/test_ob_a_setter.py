from brittle_settings import configure, get


def test_configure_defaults():
    # State-setter: leaves the settings configured for whoever runs next.
    configure(locale="en_CA")
    assert get("locale") == "en_CA"
