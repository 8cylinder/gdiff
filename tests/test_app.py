from __future__ import annotations

from pathlib import Path

from textual import containers
from textual_diff_view import DiffView

from gdiff.app import ALL_CONTEXT, DiffApp
from gdiff.gitrepo import GitRepo, Target
from gdiff.model import ChangeStatus, FileChange
from gdiff.widgets import ContextDiffView, FileList

from .conftest import commit, git, write


def _make_changes(
    repo: Path,
) -> tuple[GitRepo, list[FileChange], Target, Target]:
    write(repo, "README.md", "hello world\n")
    write(repo, "new.py", "print('hi')\n")
    git(repo, "add", "-A")
    git_repo = GitRepo(repo)
    left = Target.commit("HEAD")
    right = Target.index()
    return git_repo, git_repo.changes(left, right), left, right


def _make_big_change(
    repo: Path,
) -> tuple[GitRepo, list[FileChange], Target, Target]:
    lines = [f"line {i}" for i in range(100)]
    write(repo, "big.py", "\n".join(lines) + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "big")
    for i in range(20, 70):
        lines[i] = f"CHANGED {i}"
    write(repo, "big.py", "\n".join(lines) + "\n")
    git_repo = GitRepo(repo)
    left = Target.commit("HEAD")
    right = Target.worktree()
    return git_repo, git_repo.changes(left, right), left, right


def test_change_title_shows_both_files_for_rename() -> None:
    renamed = FileChange(ChangeStatus.RENAMED, "old.py", "new.py")
    assert DiffApp._change_title(renamed) == "old.py | new.py"


def test_change_title_shows_single_file_for_modification() -> None:
    modified = FileChange(ChangeStatus.MODIFIED, "a.py", "a.py")
    assert DiffApp._change_title(modified) == "a.py"


def test_subtitle_local_vs_head(repo: Path) -> None:
    git_repo = GitRepo(repo)
    head = git_repo.resolve("HEAD")

    assert DiffApp(git_repo, [], Target.commit(head), Target.worktree()).sub_title == (
        "local | HEAD"
    )
    assert DiffApp(git_repo, [], Target.index(), Target.worktree()).sub_title == ("local | HEAD")


def test_subtitle_local_vs_short_hash(repo: Path) -> None:
    git_repo = GitRepo(repo)
    first = git_repo.resolve("HEAD")
    write(repo, "README.md", "second\n")
    commit(repo, "second")

    app = DiffApp(git_repo, [], Target.commit(first), Target.worktree())
    assert app.sub_title == f"local | {first[:7]}"


async def test_app_loads_first_diff(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)
    assert len(changes) == 2

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        files = app.query_one(FileList)
        assert files.index == 0
        assert app.query(DiffView)


async def test_app_title_shows_current_file(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.title == changes[0].display_path
        await pilot.press("n")
        await pilot.pause()
        assert app.title == changes[1].display_path


async def test_app_navigates_between_files(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.query_one(FileList).index == 1
        await pilot.press("p")
        await pilot.pause()
        assert app.query_one(FileList).index == 0


def _equal_lines(view: ContextDiffView) -> int:
    return sum(
        i2 - i1 for group in view.grouped_opcodes for tag, i1, i2, _, _ in group if tag == "equal"
    )


def _sample_lines() -> tuple[str, str]:
    old = "\n".join(f"line{i}" for i in range(20))
    lines = [f"line{i}" for i in range(20)]
    lines[10] = "changed"
    return old, "\n".join(lines)


def test_context_diff_view_respects_context() -> None:
    old, new = _sample_lines()

    def context_lines(context: int) -> int:
        return _equal_lines(ContextDiffView("a", "b", old, new, context=context))

    assert context_lines(0) == 0
    assert context_lines(1) == 2
    assert context_lines(3) == 6
    assert context_lines(ALL_CONTEXT) == 19


def test_context_diff_view_updates_dynamically() -> None:
    old, new = _sample_lines()

    view = ContextDiffView("a", "b", old, new, context=1)
    assert _equal_lines(view) == 2
    view.context = 3
    assert _equal_lines(view) == 6


async def test_app_adjusts_context_with_keys(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right, context=5)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.context == 5
        await pilot.press("=")
        await pilot.pause()
        assert app.context == 6
        await pilot.press("=")
        await pilot.pause()
        assert app.context == 7
        await pilot.press("-")
        await pilot.pause()
        assert app.context == 6
        await pilot.press("a")
        await pilot.pause()
        assert app.context == ALL_CONTEXT
        await pilot.press("a")
        await pilot.pause()
        assert app.context == 5


async def test_app_keeps_bottom_when_adding_context(repo: Path) -> None:
    git_repo, changes, left, right = _make_big_change(repo)

    app = DiffApp(git_repo, changes, left, right, context=3)
    async with app.run_test() as pilot:
        await pilot.pause()
        container = app.query_one("#diff-container", containers.VerticalScroll)
        container.scroll_end(animate=False)
        await pilot.pause()
        assert container.is_vertical_scroll_end
        await pilot.press("=")
        await pilot.pause()
        assert container.is_vertical_scroll_end


async def test_app_keeps_relative_position_when_adding_context(repo: Path) -> None:
    git_repo, changes, left, right = _make_big_change(repo)

    app = DiffApp(git_repo, changes, left, right, context=3)
    async with app.run_test() as pilot:
        await pilot.pause()
        container = app.query_one("#diff-container", containers.VerticalScroll)
        container.scroll_to(y=15, animate=False)
        await pilot.pause()
        before = container.scroll_y / container.max_scroll_y
        await pilot.press("=")
        await pilot.pause()
        after = container.scroll_y / container.max_scroll_y
        assert abs(after - before) < 0.001


async def test_app_scrolls_two_lines_per_j_k(repo: Path) -> None:
    git_repo, changes, left, right = _make_big_change(repo)

    app = DiffApp(git_repo, changes, left, right, context=3)
    async with app.run_test() as pilot:
        await pilot.pause()
        container = app.query_one("#diff-container", containers.VerticalScroll)
        await pilot.press("j")
        await pilot.wait_for_scheduled_animations()
        assert container.scroll_y == 2
        await pilot.press("k")
        await pilot.wait_for_scheduled_animations()
        assert container.scroll_y == 0


async def test_app_pages_diff_instantly(repo: Path) -> None:
    git_repo, changes, left, right = _make_big_change(repo)

    app = DiffApp(git_repo, changes, left, right, context=3)
    async with app.run_test() as pilot:
        await pilot.pause()
        container = app.query_one("#diff-container", containers.VerticalScroll)
        assert container.scroll_y == 0
        await pilot.press("pagedown")
        # No animation: the position updates immediately, without a pause.
        assert container.scroll_y > 0
        await pilot.press("pageup")
        assert container.scroll_y == 0


async def test_app_toggles_split(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.split is True
        await pilot.press("space")
        await pilot.pause()
        assert app.split is False


async def test_app_toggles_annotations(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.annotations is True
        await pilot.press("A")
        await pilot.pause()
        assert app.annotations is False


async def test_app_cycles_themes(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = app.theme
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != before


async def test_app_toggles_sidebar(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        files = app.query_one(FileList)
        assert not files.has_class("-hidden")
        await pilot.press("s")
        await pilot.pause()
        assert files.has_class("-hidden")
