from victim_registry import register, registered


def test_register_plugin():
    # Polluter: registers a plugin and never cleans up after itself.
    register("csv")
    assert "csv" in registered()
