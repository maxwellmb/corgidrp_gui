"""The one place the GUI touches a filesystem or starts a process.

Windows and core code ask a :class:`Backend` for directory listings, FITS
headers and runner commands instead of calling ``os`` / ``subprocess``
directly, so a remote backend stays possible later.
"""
from __future__ import annotations

import abc
import fnmatch
import os
from dataclasses import dataclass, field


@dataclass
class FileEntry:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0


@dataclass
class FitsHeaders:
    path: str
    pri: dict = field(default_factory=dict)
    ext: dict = field(default_factory=dict)
    error: str | None = None

    def get(self, key: str, default=None):
        """Look a keyword up in the extension header first, then the primary."""
        if key in self.ext:
            return self.ext[key]
        return self.pri.get(key, default)


class Backend(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def listdir(self, path: str, pattern: str = "*") -> list[FileEntry]: ...

    @abc.abstractmethod
    def exists(self, path: str) -> bool: ...

    @abc.abstractmethod
    def isdir(self, path: str) -> bool: ...

    @abc.abstractmethod
    def makedirs(self, path: str) -> None: ...

    @abc.abstractmethod
    def read_headers(self, path: str) -> FitsHeaders: ...

    @abc.abstractmethod
    def python_executable(self) -> str: ...

    @abc.abstractmethod
    def home(self) -> str: ...

    def read_headers_many(self, paths: list[str]) -> list[FitsHeaders]:
        return [self.read_headers(p) for p in paths]

    def glob_fits(self, directory: str, pattern: str = "*.fits", recursive: bool = False) -> list[str]:
        out = []
        for e in self.listdir(directory):
            if e.is_dir and recursive:
                out.extend(self.glob_fits(e.path, pattern, True))
            elif not e.is_dir and fnmatch.fnmatch(e.name, pattern):
                out.append(e.path)
        return sorted(out)

    def runner_command(self, recipe_path: str, inputs_from: str | None = None,
                       outputdir: str | None = None) -> list[str]:
        """The exact command the console runs for one recipe."""
        cmd = [self.python_executable(), "-u", "-m", "corgidrp_gui.runner", recipe_path]
        if inputs_from:
            cmd += ["--inputs-from", inputs_from]
        if outputdir:
            cmd += ["--outputdir", outputdir]
        return cmd

    def join(self, *parts: str) -> str:
        return os.path.join(*parts)
