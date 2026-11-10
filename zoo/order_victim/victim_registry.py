"""A plugin registry that keeps its state in a module-level list.

Module-level state survives from one test to the next inside a pytest process,
which is the classic source of order-dependent tests.
"""

_plugins: list[str] = []


def register(name: str) -> None:
    _plugins.append(name)


def registered() -> list[str]:
    return list(_plugins)
