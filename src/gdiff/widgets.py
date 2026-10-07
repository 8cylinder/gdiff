"""List widget showing the changed files."""

from __future__ import annotations

import difflib

from rich.text import Text
from textual import containers
from textual.reactive import reactive
from textual.widgets import Label, ListItem, ListView
from textual_diff_view import DiffView

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


class ContextDiffView(DiffView):
    """A :class:`DiffView` with a configurable number of context lines."""

    context: reactive[int] = reactive(3, recompose=True)
    _scroll_anchor: tuple[bool, bool, float, int] | None = None

    def __init__(
        self,
        path_original: str,
        path_modified: str,
        code_original: str,
        code_modified: str,
        *,
        context: int = 3,
        split: bool = True,
        annotations: bool = False,
        auto_split: bool = False,
        wrap: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(
            path_original,
            path_modified,
            code_original,
            code_modified,
            split=split,
            annotations=annotations,
            auto_split=auto_split,
            wrap=wrap,
            name=name,
            id=id,
            classes=classes,
        )
        self.context = context

    def watch_context(self, context: int) -> None:
        self._grouped_opcodes = None
        self._scroll_anchor = self._capture_scroll_anchor()

    async def recompose(self) -> None:
        await super().recompose()
        anchor = self._scroll_anchor
        self._scroll_anchor = None
        if anchor is not None:
            self.call_after_refresh(lambda: self._restore_scroll_anchor(anchor))

    def _capture_scroll_anchor(self) -> tuple[bool, bool, float, int] | None:
        container = self._scroll_container()
        if container is None:
            return None
        return (
            container.is_vertical_scroll_end,
            container.scroll_y <= 0,
            container.scroll_y,
            container.max_scroll_y,
        )

    def _restore_scroll_anchor(self, anchor: tuple[bool, bool, float, int]) -> None:
        container = self._scroll_container()
        if container is None:
            return
        at_end, at_home, scroll_y, max_scroll = anchor
        if at_end:
            container.scroll_end(animate=False)
        elif at_home:
            container.scroll_home(animate=False)
        elif max_scroll:
            ratio = scroll_y / max_scroll
            container.scroll_to(y=ratio * container.max_scroll_y, animate=False)

    def _scroll_container(self) -> containers.VerticalScroll | None:
        parent = self.parent
        return parent if isinstance(parent, containers.VerticalScroll) else None

    @property
    def grouped_opcodes(self) -> list[list[tuple[str, int, int, int, int]]]:
        if self._grouped_opcodes is None:
            text_lines_a = self.code_original.splitlines()
            text_lines_b = self.code_modified.splitlines()
            sequence_matcher = difflib.SequenceMatcher(
                lambda character: character in {" ", "\t"},
                text_lines_a,
                text_lines_b,
                autojunk=True,
            )
            self._grouped_opcodes = list(sequence_matcher.get_grouped_opcodes(self.context))
        return self._grouped_opcodes
