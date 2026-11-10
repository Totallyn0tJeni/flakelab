"""Application settings held in a module-level dict that starts empty."""

_settings: dict[str, str] = {}


def configure(**values: str) -> None:
    _settings.update(values)


def get(key: str) -> str:
    return _settings[key]
