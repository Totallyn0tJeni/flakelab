def test_first_tag_is_alpha():
    # Sets of strings have no fixed order: it depends on the hash seed Python
    # picks at startup, so the outcome is stable within a process and varies
    # between processes.
    tags = {"alpha", "beta", "gamma", "delta"}
    assert next(iter(tags)) == "alpha"
