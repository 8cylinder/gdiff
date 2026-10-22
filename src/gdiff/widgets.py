"""List widget showing the changed files."""

from __future__ import annotations

import difflib
from math import ceil

from rich.text import Text
from textual import containers
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView
from textual_diff_view import DiffView

from gdiff.model import ChangeStatus, FileChange

ALL_CONTEXT = 1 << 30

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
    _last_finite_context: int = 3

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
        self._last_finite_context = context if context < ALL_CONTEXT else 3
        self.context = context

    def watch_context(self, context: int) -> None:
        if context < ALL_CONTEXT:
            self._last_finite_context = context
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
        at_home = container.scroll_y <= 0
        return (
            not at_home and container.is_vertical_scroll_end,
            at_home,
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

    def _grouped_opcodes_for(self, context: int) -> list[list[tuple[str, int, int, int, int]]]:
        text_lines_a = self.code_original.splitlines()
        text_lines_b = self.code_modified.splitlines()
        sequence_matcher = difflib.SequenceMatcher(
            lambda character: character in {" ", "\t"},
            text_lines_a,
            text_lines_b,
            autojunk=True,
        )
        return list(sequence_matcher.get_grouped_opcodes(context))

    @property
    def grouped_opcodes(self) -> list[list[tuple[str, int, int, int, int]]]:
        if self._grouped_opcodes is None:
            self._grouped_opcodes = self._grouped_opcodes_for(self.context)
        return self._grouped_opcodes

    def chunk_offsets(self) -> list[int]:
        """Scroll offsets of the first changed line in each diff chunk.

        Offsets are relative to the scroll container, so they can be passed
        directly to :meth:`~textual.widget.Widget.scroll_to`. Chunks are based
        on the current context, except in the all-lines view where they use the
        last finite context so that navigation remains useful.
        """
        groups = self._grouped_opcodes_for(self._last_finite_context)
        chunk_starts = {start for group in groups if (start := _first_change(group)) is not None}

        display_groups = self.grouped_opcodes
        group_widgets = list(self.query(".diff-group"))
        if len(group_widgets) != len(display_groups):
            return []

        offsets: list[int] = []
        for group_widget, opcodes in zip(group_widgets, display_groups, strict=True):
            offsets.extend(self._chunk_offsets_in_group(group_widget, opcodes, chunk_starts))
        return offsets

    def _chunk_offsets_in_group(
        self,
        group_widget: Widget,
        opcodes: list[tuple[str, int, int, int, int]],
        chunk_starts: set[tuple[str, int, int, int, int]],
    ) -> list[int]:
        base = self.virtual_region.y + group_widget.virtual_region.y
        rows = self._opcode_rows(group_widget, opcodes)
        offsets: list[int] = []
        row = 0
        for opcode, count in zip(opcodes, rows, strict=True):
            if opcode in chunk_starts:
                offsets.append(base + row)
            row += count
        return offsets

    def _opcode_rows(
        self,
        group_widget: Widget,
        opcodes: list[tuple[str, int, int, int, int]],
    ) -> list[int]:
        """Rows rendered by each opcode, accounting for split and wrap modes."""
        counts = [_opcode_lines(opcode, split=self.split) for opcode in opcodes]
        if not self.wrap:
            return counts

        heights = self._wrapped_line_heights(group_widget)
        if not heights:
            return counts

        rows: list[int] = []
        line = 0
        for count in counts:
            end = line + count
            rows.append(sum(heights[line:end]))
            line = end
        return rows

    def _wrapped_line_heights(self, group_widget: Widget) -> list[int]:
        codes = list(group_widget.query("DiffCode"))
        if not codes:  # pragma: no cover - layout not ready
            return []
        code = codes[0]
        visual = getattr(code, "content", None)
        annotations = getattr(visual, "annotations", None)
        code_lengths = getattr(visual, "code_lengths", None)
        width = code.size.width
        if annotations is None or code_lengths is None or not width:
            return []
        return [
            ceil(length / max(1, width - annotation.cell_length)) if length else 1
            for annotation, length in zip(annotations, code_lengths, strict=True)
        ]


def _first_change(
    group: list[tuple[str, int, int, int, int]],
) -> tuple[str, int, int, int, int] | None:
    for opcode in group:
        if opcode[0] != "equal":
            return opcode
    return None


def _opcode_lines(opcode: tuple[str, int, int, int, int], *, split: bool) -> int:
    tag, i1, i2, j1, j2 = opcode
    removed = i2 - i1
    added = j2 - j1
    if tag == "equal":
        return removed
    if tag == "delete":
        return removed
    if tag == "insert":
        return added
    return max(removed, added) if split else removed + added
