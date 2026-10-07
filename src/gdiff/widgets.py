"""List widget showing the changed files."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Label, ListItem, ListView

from gdiff.model import ChangeStatus, FileChange

_STATUS_STYLE: dict[ChangeStatus, str] = {
    ChangeStatus.ADDED: "bold green",
    ChangeStatus.DELETED: "bold red",
    ChangeStatus.MODIFIED: "bold yellow",
    ChangeStatus.RENAMED: "bold cyan",
    ChangeStatus.COPIED: "bold cyan",
    ChangeStatus.TYPE_CHANGED: "bold magenta",
    ChangeStatus.UNMERGED: "bold red",
    ChangeStatus.UNKNOWN: "bold white",
}


def format_change(change: FileChange) -> Text:
    """Render a change as a coloured status letter plus its path."""
    text = Text()
    style = _STATUS_STYLE.get(change.status, "bold white")
    text.append(f"{change.status.single_letter} ", style=style)
    text.append(change.display_path)
    return text


class FileItem(ListItem):
    """A single row in the :class:`FileList`."""

    def __init__(self, change: FileChange) -> None:
        super().__init__(Label(format_change(change)))
        self.change = change


class FileList(ListView):
    """Scrollable list of the files that differ."""

    def __init__(
        self,
        changes: list[FileChange],
        *,
        id: str | None = None,
        name: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, name=name, classes=classes)
        self.changes = changes

    def on_mount(self) -> None:
        for change in self.changes:
            self.append(FileItem(change))
