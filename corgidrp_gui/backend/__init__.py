"""Filesystem and process access behind one interface."""
from .base import Backend, FileEntry, FitsHeaders
from .local import LocalBackend

_default: Backend | None = None


def default_backend() -> Backend:
    global _default
    if _default is None:
        _default = LocalBackend()
    return _default


def set_default_backend(b: Backend):
    global _default
    _default = b


__all__ = ["Backend", "FileEntry", "FitsHeaders", "LocalBackend", "default_backend", "set_default_backend"]
