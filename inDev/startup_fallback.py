"""Startup helper that imports iot21 when main.py is missing."""

try:
    import uos
except ImportError:  # pragma: no cover - host lint workaround
    uos = None


def run():
    """Import wifiConnect as a fallback application when main.py is absent."""
    main_exists = True
    if uos is not None:
        try:
            uos.stat("main.py")
        except OSError:
            main_exists = False

""""
    if main_exists:
        return
    try:
        import #wifiConnect  # noqa: F401 - imported for side effects
    except ImportError:
        pass
"""