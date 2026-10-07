"""Domain model for gdiff."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChangeStatus(StrEnum):
    """The kind of change applied to a file."""

    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    TYPE_CHANGED = "T"
    RENAMED = "R"
    COPIED = "C"
    UNMERGED = "U"
    UNKNOWN = "?"

    @classmethod
    def from_code(cls, code: str) -> ChangeStatus:
        """Map a single-letter git status code to a :class:`ChangeStatus`."""
        try:
            return cls(code.upper())
        except ValueError:
            return cls.UNKNOWN

    @property
    def single_letter(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FileChange:
    """A single file entry in a diff.

    ``old_path`` is ``None`` for added files and ``new_path`` is ``None`` for
    deleted files. For modifications both point at the same path.
    """

    status: ChangeStatus
    old_path: str | None
    new_path: str | None

    @property
    def display_path(self) -> str:
        """A human readable path, showing both sides of a rename."""
        if self.status is ChangeStatus.RENAMED and self.old_path and self.new_path:
            return f"{self.old_path} \u2192 {self.new_path}"
        return self.new_path or self.old_path or ""

    @property
    def key(self) -> tuple[str | None, str | None]:
        return (self.old_path, self.new_path)
