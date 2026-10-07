from __future__ import annotations

from pathlib import Path

from gdiff.gitrepo import GitRepo, Target, _parse_name_status, is_binary
from gdiff.model import ChangeStatus

from .conftest import commit, write


def test_parse_name_status_add_modify_delete() -> None:
    data = b"A\0new.py\0M\0mod.py\0D\0gone.py\0"
    changes = _parse_name_status(data)
    assert [(c.status, c.old_path, c.new_path) for c in changes] == [
        (ChangeStatus.ADDED, None, "new.py"),
        (ChangeStatus.MODIFIED, "mod.py", "mod.py"),
        (ChangeStatus.DELETED, "gone.py", None),
    ]


def test_parse_name_status_rename() -> None:
    data = b"R100\0old.py\0new.py\0"
    (change,) = _parse_name_status(data)
    assert change.status is ChangeStatus.RENAMED
    assert change.old_path == "old.py"
    assert change.new_path == "new.py"
    assert change.display_path == "old.py \u2192 new.py"


def test_worktree_vs_index(repo: Path) -> None:
    write(repo, "README.md", "hello world\n")
    git_repo = GitRepo(repo)
    changes = git_repo.changes(Target.index(), Target.worktree())
    assert [(c.status, c.new_path) for c in changes] == [(ChangeStatus.MODIFIED, "README.md")]


def test_staged_changes(repo: Path) -> None:
    write(repo, "README.md", "hello world\n")
    write(repo, "added.txt", "new file\n")
    git_repo = GitRepo(repo)
    git_repo._run(["add", "-A"])
    changes = git_repo.changes(Target.commit("HEAD"), Target.index())
    statuses = {c.new_path: c.status for c in changes}
    assert statuses["README.md"] is ChangeStatus.MODIFIED
    assert statuses["added.txt"] is ChangeStatus.ADDED


def test_two_commit_range(repo: Path) -> None:
    write(repo, "README.md", "first\n")
    first = commit(repo, "c1")
    write(repo, "README.md", "second\n")
    write(repo, "extra.py", "print('hi')\n")
    second = commit(repo, "c2")

    changes = GitRepo(repo).changes(Target.commit(first), Target.commit(second))
    assert {(c.status, c.new_path) for c in changes} == {
        (ChangeStatus.MODIFIED, "README.md"),
        (ChangeStatus.ADDED, "extra.py"),
    }


def test_blob_reads_both_sides(repo: Path) -> None:
    write(repo, "file.txt", "one\n")
    first = commit(repo, "c1")
    write(repo, "file.txt", "two\n")
    second = commit(repo, "c2")

    git_repo = GitRepo(repo)
    assert git_repo.blob(Target.commit(first), "file.txt") == b"one\n"
    assert git_repo.blob(Target.commit(second), "file.txt") == b"two\n"
    assert git_repo.blob(Target.commit(second), "missing.txt") == b""
    assert git_repo.blob(Target.commit(second), None) == b""


def test_rename_detection(repo: Path) -> None:
    write(repo, "long_name.py", "x = 1\n" * 40)
    first = commit(repo, "c1")
    (repo / "long_name.py").rename(repo / "renamed.py")
    second = commit(repo, "c2")

    changes = GitRepo(repo).changes(Target.commit(first), Target.commit(second))
    assert len(changes) == 1
    assert changes[0].status is ChangeStatus.RENAMED
    assert changes[0].old_path == "long_name.py"
    assert changes[0].new_path == "renamed.py"


def test_path_filter(repo: Path) -> None:
    write(repo, "a.txt", "a\n")
    write(repo, "b.txt", "b\n")
    git_repo = GitRepo(repo)
    git_repo._run(["add", "-A"])
    commit(repo, "add files")

    write(repo, "a.txt", "changed a\n")
    write(repo, "b.txt", "changed b\n")
    changes = git_repo.changes(Target.index(), Target.worktree(), paths=["a.txt"])
    assert [c.new_path for c in changes] == ["a.txt"]


def test_binary_detection() -> None:
    assert not is_binary(b"plain text\n")
    assert not is_binary(b"\x89PNG\r\n\x1a\n")
    assert is_binary(b"abc\0def")
