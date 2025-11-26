"""Centralized module version declarations for the eBikeWatch project."""

APP_VERSION = "2025.11.26.1"

MODULE_VERSIONS = {
    "t": APP_VERSION,
    "motor_control": APP_VERSION,
    "runtime.motor": APP_VERSION,
}


def module_version(name, default=None):
    """Return the registered version for *name* (defaults to APP_VERSION)."""
    if not name:
        return default if default is not None else APP_VERSION
    return MODULE_VERSIONS.get(name, default if default is not None else APP_VERSION)
