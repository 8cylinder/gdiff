"""Command line entry point for gdiff."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
from click.shell_completion import get_completion_class

from gdiff import __version__
from gdiff.app import ALL_CONTEXT, DiffApp
from gdiff.gitrepo import GitError, GitRepo, Target

DESCRIPTION = "A terminal UI replacement for `git diff`."

EXAMPLES = """\
examples:
  gdiff                       working tree vs index (like `git diff`)
  gdiff HEAD                  HEAD vs the working tree
  gdiff 1a2b3c4               a commit hash vs the working tree
  gdiff file1 file2           compare two files on disk
  gdiff main feature          two commits
  gdiff HEAD~1 HEAD -- src/   two commits, limited to a path
  gdiff -- a.py b.py          limit the diff to two file paths
"""

COMPLETE_VAR = "_GDIFF_COMPLETE"


@dataclass(slots=True)
class Options:
    """Parsed command line options."""

    revs: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    staged: bool = False
    find_renames: bool = True
    context: int = 3


def _is_file_pair(args: list[str]) -> bool:
    """Whether ``args`` are exactly two paths to existing files."""
    return (
        len(args) == 2
        and not any(arg.startswith("-") for arg in args)
        and all(Path(arg).is_file() for arg in args)
    )


def _split_paths(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


def _context_value(value: str) -> int:
    """Parse a context count, where ``a`` means every line in the file."""
    if value.lower() == "a":
        return ALL_CONTEXT
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{value!r} is not an integer") from None
    if number < 0:
        raise ValueError("context must not be negative")
    return number


class ContextParam(click.ParamType):
    """A non-negative context count, or ``a`` for the whole file."""

    name = "N"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int:
        if isinstance(value, int):
            return value
        if not isinstance(value, str):
            self.fail(f"{value!r} is not an integer", param, ctx)
        try:
            return _context_value(value)
        except ValueError as error:
            self.fail(str(error), param, ctx)


def _completion_path() -> Path:
    return Path.home() / ".local/share/bash-completion/completions/gdiff"


def _completion_script(command: click.Command) -> str:
    completion_class = get_completion_class("bash")
    if completion_class is None:
        raise RuntimeError("bash completion is not available")
    completion = completion_class(
        cli=command,
        ctx_args={},
        prog_name="gdiff",
        complete_var=COMPLETE_VAR,
    )
    return completion.source()


def _write_completions(ctx: click.Context, param: click.Parameter | None, value: bool) -> None:
    """Write the bash completion script and exit."""
    if not value or ctx.resilient_parsing:
        return

    path = _completion_path()
    try:
        script = _completion_script(ctx.command)
    except (OSError, RuntimeError) as error:
        click.echo(f"gdiff: {error}", err=True)
        ctx.exit(1)
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script, encoding="utf-8")
    except OSError as error:
        click.echo(f"gdiff: could not write {path}: {error}", err=True)
        ctx.exit(1)
        return

    click.echo(f"wrote completion script to {path}")
    click.echo(f"source it with: source {path}")
    ctx.exit()


def _check_revs(revs: list[str]) -> None:
    if len(revs) > 2:
        raise click.UsageError("at most two revisions may be given")


@click.command(
    name="gdiff",
    help=DESCRIPTION,
    epilog="\b\n" + EXAMPLES,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="gdiff", message="%(prog)s %(version)s")
@click.option(
    "--completions",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_write_completions,
    help="write the bash completion script and exit",
)
@click.option(
    "--staged",
    "--cached",
    "staged",
    is_flag=True,
    help="compare staged changes instead of the working tree",
)
@click.option(
    "-c",
    "--context",
    type=ContextParam(),
    default=3,
    show_default=True,
    metavar="N",
    help="show N lines of context around each change, or 'a' for the whole file",
)
@click.option(
    "-M",
    "--find-renames/--no-renames",
    default=True,
    help="detect renames (default) or disable rename detection",
)
@click.argument("revs", nargs=-1)
@click.pass_context
def cli(
    ctx: click.Context,
    revs: tuple[str, ...],
    staged: bool,
    context: int,
    find_renames: bool,
) -> int:
    """A terminal UI replacement for `git diff`."""
    paths: list[str] = ctx.obj if isinstance(ctx.obj, list) else []
    return run(
        Options(
            revs=list(revs),
            paths=paths,
            staged=staged,
            find_renames=find_renames,
            context=context,
        )
    )


def parse_args(argv: list[str]) -> Options:
    main_args, paths = _split_paths(list(argv))
    ctx = cli.make_context("gdiff", main_args, obj=paths)
    revs = list(ctx.params["revs"])
    _check_revs(revs)

    files: list[str] = []
    if _is_file_pair(revs):
        files = revs
        revs = []

    return Options(
        revs=revs,
        paths=paths,
        files=files,
        staged=ctx.params["staged"],
        find_renames=ctx.params["find_renames"],
        context=ctx.params["context"],
    )


def resolve_targets(repo: GitRepo, options: Options) -> tuple[Target, Target]:
    """Translate the parsed revisions into the two sides of the diff."""
    if len(options.files) == 2:
        return Target.file(options.files[0]), Target.file(options.files[1])

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
    except ValueError as error:
        click.echo(f"gdiff: {error}", err=True)
        return 2

    if _is_file_pair(args):
        command = ["git", "diff", "--no-index"]
        if context is not None:
            command.append(f"--unified={context}")
        command.extend(["--", *args])
    else:
        command = ["git", "diff"]
        if context is not None:
            command.append(f"--unified={context}")
        command.extend(args)
    try:
        return subprocess.call(command)
    except FileNotFoundError:
        click.echo("gdiff: git not found on PATH", err=True)
        return 127


def run(options: Options) -> int:
    """Run the diff viewer for the given options."""
    _check_revs(options.revs)
    repo = GitRepo(Path.cwd())
    if not options.files and not repo.is_repo():
        click.echo("gdiff: not a git repository", err=True)
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
        click.echo(f"gdiff: {error}", err=True)
        return 128

    if not changes:
        click.echo("gdiff: no changes", err=True)
        return 0

    DiffApp(repo, changes, left, right, options.context).run()
    return 0


def _wants_click(args: list[str]) -> bool:
    """Whether non-interactive args should be handled by click."""
    return any(arg in ("-h", "--help", "--version", "--completions") for arg in args)


def _invoke_click(args: list[str], paths: list[str] | None = None) -> int:
    result = cli.main(
        args=args,
        prog_name="gdiff",
        complete_var=COMPLETE_VAR,
        standalone_mode=False,
        obj=paths,
    )
    return result if isinstance(result, int) else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    main_args, paths = _split_paths(argv)

    if COMPLETE_VAR in os.environ:
        return _invoke_click(argv)

    if not (sys.stdout.isatty() and sys.stdin.isatty()):
        if _wants_click(main_args):
            return _invoke_click(main_args)
        return _passthrough(argv)

    try:
        return _invoke_click(main_args, paths)
    except click.UsageError as error:
        click.echo(f"gdiff: {error.format_message()}", err=True)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
