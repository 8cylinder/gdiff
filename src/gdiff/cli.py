"""Command line entry point for gdiff."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from gdiff import __version__
from gdiff.app import ALL_CONTEXT, DiffApp
from gdiff.gitrepo import GitError, GitRepo, Target

DESCRIPTION = "A terminal UI replacement for `git diff`."


@dataclass(slots=True)
class Options:
    """Parsed command line options."""

    revs: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    staged: bool = False
    find_renames: bool = True
    context: int = 3


def _split_paths(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if number < 0:
        raise argparse.ArgumentTypeError("context must not be negative")
    return number


def _context_value(value: str) -> int:
    """Parse a context count, where ``a`` means every line in the file."""
    if value.lower() == "a":
        return ALL_CONTEXT
    return _non_negative_int(value)


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
    parser.add_argument(
        "-c",
        "--context",
        type=_context_value,
        default=3,
        metavar="N",
        help="show N lines of context around each change, or 'a' for the whole file (default: 3)",
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
        context=ns.context,
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


def _extract_context(argv: list[str]) -> tuple[list[str], int | None]:
    """Pull ``-c``/``--context`` out of ``argv`` for a plain ``git diff``."""
    stripped: list[str] = []
    context: int | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-c", "--context") and index + 1 < len(argv):
            context = _context_value(argv[index + 1])
            index += 2
        elif arg.startswith("--context="):
            context = _context_value(arg.split("=", 1)[1])
            index += 1
        elif arg.startswith("-c") and len(arg) > 2:
            context = _context_value(arg[2:])
            index += 1
        else:
            stripped.append(arg)
            index += 1
    return stripped, context


def _passthrough(argv: list[str]) -> int:
    """When stdout is not a TTY, behave like plain ``git diff``."""
    try:
        args, context = _extract_context(argv)
    except argparse.ArgumentTypeError as error:
        print(f"gdiff: {error}", file=sys.stderr)
        return 2
    command = ["git", "diff"]
    if context is not None:
        command.append(f"--unified={context}")
    command.extend(args)
    try:
        return subprocess.call(command)
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

    DiffApp(repo, changes, left, right, options.context).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
