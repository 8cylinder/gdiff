from __future__ import annotations

from pathlib import Path

from textual_diff_view import DiffView

from gdiff.app import DiffApp
from gdiff.gitrepo import GitRepo, Target
from gdiff.model import FileChange
from gdiff.widgets import FileList

from .conftest import git, write


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


async def test_app_loads_first_diff(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)
    assert len(changes) == 2

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        files = app.query_one(FileList)
        assert files.index == 0
        assert app.query(DiffView)


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


async def test_app_toggles_split(repo: Path) -> None:
    git_repo, changes, left, right = _make_changes(repo)

    app = DiffApp(git_repo, changes, left, right)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.split is True
        await pilot.press("space")
        await pilot.pause()
        assert app.split is False
