"""The Textual application."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from textual import containers, widgets
from textual.app import App, ComposeResult
from textual.reactive import var
from textual_diff_view import DiffView, LoadError

from gdiff.gitrepo import GitRepo, Target, is_binary
from gdiff.model import FileChange
from gdiff.widgets import FileItem, FileList


class DiffApp(App[None]):
    """Browse a repository diff one file at a time."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    FileList {
        width: 40%;
        min-width: 20;
        border-right: solid $panel;
    }

    #diff-container {
        width: 1fr;
        padding: 0 1;
    }

    .placeholder {
        padding: 1 2;
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("space", "toggle_split", "Split"),
        ("a", "toggle_annotations", "Annotations"),
        ("w", "toggle_wrap", "Wrap"),
        ("n", "next_file", "Next"),
        ("p", "previous_file", "Previous"),
    ]

    split = var(True)
    annotations = var(True)
    wrap = var(False)

    def __init__(
        self,
        repo: GitRepo,
        changes: list[FileChange],
        left: Target,
        right: Target,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.changes = changes
        self.left = left
        self.right = right
        self.sub_title = f"{left.label} \u2192 {right.label}"
        self._current: tuple[str | None, str | None] | None = None
        self._request = 0

    def compose(self) -> ComposeResult:
        yield widgets.Header(show_clock=False)
        with containers.Horizontal(id="body"):
            yield FileList(self.changes, id="files")
            yield containers.VerticalScroll(id="diff-container")
        yield widgets.Footer()

    def on_mount(self) -> None:
        files = self.query_one(FileList)
        files.focus()
        if self.changes:
            self.run_worker(self._show_change(self.changes[0]), exclusive=True)

    async def on_list_view_highlighted(self, event: widgets.ListView.Highlighted) -> None:
        if isinstance(event.item, FileItem):
            await self._show_change(event.item.change)

    async def _show_change(self, change: FileChange) -> None:
        container = self.query_one("#diff-container", containers.VerticalScroll)

        if change.key == self._current:
            return
        self._current = change.key
        self._request += 1
        request = self._request

        await container.remove_children()
        await container.mount(widgets.Static("Loading\u2026", classes="placeholder"))

        old_bytes = await asyncio.to_thread(self.repo.blob, self.left, change.old_path)
        new_bytes = await asyncio.to_thread(self.repo.blob, self.right, change.new_path)

        if request != self._request:
            return

        await container.remove_children()

        if is_binary(old_bytes) or is_binary(new_bytes):
            await container.mount(widgets.Static("Binary file not shown.", classes="placeholder"))
            return

        old_label = self._side_label(self.left, change.old_path)
        new_label = self._side_label(self.right, change.new_path)
        try:
            view = DiffView(
                old_label,
                new_label,
                old_bytes.decode("utf-8", "replace"),
                new_bytes.decode("utf-8", "replace"),
            )
        except LoadError as error:  # pragma: no cover - defensive
            await container.mount(widgets.Static(str(error), classes="placeholder"))
            return

        view.data_bind(DiffApp.split, DiffApp.annotations, DiffApp.wrap)

        if request != self._request:
            return
        await container.mount(view)

    @staticmethod
    def _side_label(target: Target, path: str | None) -> str:
        if path is None:
            return "/dev/null"
        return f"{target.label}:{path}"

    def action_toggle_split(self) -> None:
        self.split = not self.split

    def action_toggle_annotations(self) -> None:
        self.annotations = not self.annotations

    def action_toggle_wrap(self) -> None:
        self.wrap = not self.wrap

    def action_next_file(self) -> None:
        self.query_one(FileList).action_cursor_down()

    def action_previous_file(self) -> None:
        self.query_one(FileList).action_cursor_up()
