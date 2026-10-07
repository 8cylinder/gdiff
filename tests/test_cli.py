from __future__ import annotations

from pathlib import Path

import pytest

from gdiff.cli import ALL_CONTEXT, main, parse_args, resolve_targets
from gdiff.gitrepo import GitRepo, Target, TargetKind

from .conftest import commit, write


def test_defaults() -> None:
    options = parse_args([])
    assert options.revs == []
    assert options.paths == []
    assert options.staged is False
    assert options.find_renames is True


def test_two_revisions_and_paths() -> None:
    options = parse_args(["main", "feature", "--", "a.py", "b.py"])
    assert options.revs == ["main", "feature"]
    assert options.paths == ["a.py", "b.py"]


def test_staged_and_cached_aliases() -> None:
    assert parse_args(["--staged"]).staged is True
    assert parse_args(["--cached"]).staged is True


def test_no_renames() -> None:
    assert parse_args(["--no-renames"]).find_renames is False
    assert parse_args(["-M"]).find_renames is True


def test_context_default_and_flags() -> None:
    assert parse_args([]).context == 3
    assert parse_args(["-c", "5"]).context == 5
    assert parse_args(["--context", "0"]).context == 0
    assert parse_args(["--context=10"]).context == 10


def test_context_a_means_whole_file() -> None:
    assert parse_args(["-c", "a"]).context == ALL_CONTEXT
    assert parse_args(["--context=A"]).context == ALL_CONTEXT


def test_context_rejects_negative() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--context", "-1"])


def test_too_many_revisions() -> None:
    with pytest.raises(SystemExit):
        parse_args(["a", "b", "c"])


def test_resolve_default_is_index_worktree(repo: Path) -> None:
    left, right = resolve_targets(GitRepo(repo), parse_args([]))
    assert left.kind is TargetKind.INDEX
    assert right.kind is TargetKind.WORKTREE


def test_resolve_staged_is_head_index(repo: Path) -> None:
    left, right = resolve_targets(GitRepo(repo), parse_args(["--staged"]))
    assert left.kind is TargetKind.COMMIT
    assert right.kind is TargetKind.INDEX


def test_resolve_two_commits(repo: Path) -> None:
    write(repo, "README.md", "first\n")
    first = commit(repo, "c1")
    write(repo, "README.md", "second\n")
    second = commit(repo, "c2")
    left, right = resolve_targets(GitRepo(repo), parse_args([first, second]))
    assert left == Target.commit(first)
    assert right == Target.commit(second)


def test_resolve_one_commit_hash(repo: Path) -> None:
    write(repo, "README.md", "first\n")
    first = commit(repo, "c1")
    left, right = resolve_targets(GitRepo(repo), parse_args([first]))
    assert left == Target.commit(first)
    assert right.kind is TargetKind.WORKTREE


def test_resolve_one_commit_hash_staged(repo: Path) -> None:
    write(repo, "README.md", "first\n")
    first = commit(repo, "c1")
    left, right = resolve_targets(GitRepo(repo), parse_args([first, "--staged"]))
    assert left == Target.commit(first)
    assert right.kind is TargetKind.INDEX


def test_help_is_handled_without_tty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("gdiff.cli.sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.sys.stdin.isatty", lambda: False)
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "usage: gdiff" in out
    assert "gdiff HEAD" in out
    assert "a commit hash" in out
    assert "gdiff -- a.py b.py" in out


def test_passthrough_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("gdiff.cli.sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.subprocess.call", lambda args: calls.append(args) or 0)

    assert main(["HEAD~1", "HEAD", "--", "a.py"]) == 0
    assert calls == [["git", "diff", "HEAD~1", "HEAD", "--", "a.py"]]


def test_passthrough_translates_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("gdiff.cli.sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.subprocess.call", lambda args: calls.append(args) or 0)

    assert main(["-c", "7", "HEAD", "--", "a.py"]) == 0
    assert calls == [["git", "diff", "--unified=7", "HEAD", "--", "a.py"]]


def test_passthrough_translates_full_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("gdiff.cli.sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("gdiff.cli.subprocess.call", lambda args: calls.append(args) or 0)

    assert main(["-c", "a", "HEAD"]) == 0
    assert calls == [["git", "diff", f"--unified={ALL_CONTEXT}", "HEAD"]]
