"""Command line entry point for gdiff."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from gdiff import __version__
from gdiff.app import DiffApp
from gdiff.gitrepo import GitError, GitRepo, Target

DESCRIPTION = "A terminal UI replacement for `git diff`."


@dataclass(slots=True)
class Options:
    """Parsed command line options."""

    revs: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    staged: bool = False
    find_renames: bool = True


def _split_paths(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gdiff", description=DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"gdiff {__version__}",
    )
    parser.add_argument(
        "revs",
        nargs="*",
        metavar="REV",
        help="zero, one, or two revisions to compare",
    )
    parser.add_argument(
        "--staged",
        "--cached",
        action="store_true",
        help="compare staged changes instead of the working tree",
    )
    rename = parser.add_mutually_exclusive_group()
    rename.add_argument(
        "-M",
        "--find-renames",
        action="store_true",
        dest="find_renames",
        help="detect renames (default)",
    )
    rename.add_argument(
        "--no-renames",
        action="store_false",
        dest="find_renames",
        help="disable rename detection",
    )
    parser.set_defaults(find_renames=True)
    return parser


def parse_args(argv: list[str]) -> Options:
    main, paths = _split_paths(list(argv))
    parser = build_parser()
    ns = parser.parse_args(main)
    if len(ns.revs) > 2:
        parser.error("at most two revisions may be given")
    return Options(
        revs=ns.revs,
        paths=paths,
        staged=ns.staged,
        find_renames=ns.find_renames,
    )


def resolve_targets(repo: GitRepo, options: Options) -> tuple[Target, Target]:
    """Translate the parsed revisions into the two sides of the diff."""
    if len(options.revs) == 2:
        left = Target.commit(repo.resolve(options.revs[0]))
        right = Target.commit(repo.resolve(options.revs[1]))
        return left, right

    if len(options.revs) == 1:
        base = repo.resolve(options.revs[0])
        right = Target.index() if options.staged else Target.worktree()
        return Target.commit(base), right

    head = repo.resolve("HEAD")
    if options.staged:
        return Target.commit(head), Target.index()
    return Target.index(), Target.worktree()


def _passthrough(argv: list[str]) -> int:
    """When stdout is not a TTY, behave like plain ``git diff``."""
    try:
        return subprocess.call(["git", "diff", *argv])
    except FileNotFoundError:
        print("gdiff: git not found on PATH", file=sys.stderr)
        return 127


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if any(arg in ("-h", "--help") for arg in argv):
        build_parser().print_help()
        return 0
    if "--version" in argv:
        print(f"gdiff {__version__}")
        return 0

    if not (sys.stdout.isatty() and sys.stdin.isatty()):
        return _passthrough(argv)

    options = parse_args(argv)
    repo = GitRepo(Path.cwd())
    if not repo.is_repo():
        print("gdiff: not a git repository", file=sys.stderr)
        return 128

    try:
        left, right = resolve_targets(repo, options)
        changes = repo.changes(
            left,
            right,
            paths=options.paths,
            find_renames=options.find_renames,
        )
    except GitError as error:
        print(f"gdiff: {error}", file=sys.stderr)
        return 128

    if not changes:
        print("gdiff: no changes", file=sys.stderr)
        return 0

    DiffApp(repo, changes, left, right).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
