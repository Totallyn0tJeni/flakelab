from victim_registry import registered


def test_registry_starts_empty():
    # Victim: passes alone, fails whenever the polluter has run first.
    assert registered() == []
