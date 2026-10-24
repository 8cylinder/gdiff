# gdiff

A terminal UI replacement for `git diff`, built with
[Textual](https://github.com/textualize/textual) and
[textual-diff-view](https://github.com/batrachianai/textual-diff-view).

`gdiff` resolves revisions with git plumbing and renders each changed file in a
side-by-side or unified diff view.

Source: <https://github.com/8cylinder/gdiff>

## Install

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and git.

From a checkout:

```sh
git clone git@github.com:8cylinder/gdiff.git
cd gdiff
uv sync            # install dependencies
uv run gdiff       # run from the checkout
```

Install the CLI as a tool:

```sh
make install       # uv tool install --editable --force .
gdiff --version
```

## Usage

```sh
gdiff                       # working tree vs index (like `git diff`)
gdiff HEAD                  # HEAD vs working tree
gdiff 1a2b3c4               # a commit hash vs working tree
gdiff main feature          # two commits
gdiff file1 file2           # compare two files on disk
gdiff --staged              # index vs HEAD
gdiff HEAD~1 HEAD -- src/   # limit to a pathspec
gdiff -- a.py b.py          # limit the diff to specific files
```

When both positional arguments are existing files, `gdiff` compares those two
files directly (like `git diff --no-index`) instead of treating them as
revisions. This works even outside a git repository.

Pass pathspecs after `--` so they are not parsed as revisions. The header
shows the current file and the subtitle shows the two sides, e.g. `local | HEAD`
or `local | 1a2b3c4`.

`gdiff -h` prints the same examples.

### Options

| Option                    | Meaning                                              |
| ------------------------- | ---------------------------------------------------- |
| `--staged`, `--cached`    | Compare the index instead of the working tree        |
| `-c N`, `--context N`     | Show `N` context lines around each change (`a` = all)|
| `-M`, `--find-renames`    | Detect renames (default)                             |
| `--no-renames`            | Disable rename detection                             |
| `--completions`           | Write the bash completion script and exit            |
| `-h`, `--help`            | Print help and the examples                          |
| `--version`               | Print the version                                    |

`gdiff` has no configuration file; all options are command-line flags. The
version is read from the package metadata generated from `pyproject.toml`.

When stdout is not a terminal (a pipe or redirect), `gdiff` delegates to
`git diff` so it stays scriptable (a `-c`/`--context` value is translated to
`--unified`).

### Shell completion

```sh
gdiff --completions
```

This writes a bash completion script to
`~/.local/share/bash-completion/completions/gdiff`, prints the path, and tells
you how to source it. Run the printed `source` command to enable completion in
the current terminal.

### Keys

| Key              | Action                                          |
| ---------------- | ----------------------------------------------- |
| `n` / `p`        | Next / previous file                            |
| `Alt+n` / `Alt+p` | Next / previous diff chunk                      |
| `j` / `k`        | Scroll the diff down / up (two lines)           |
| `PageUp`/`PageDown` | Page the diff up / down                      |
| `space`          | Toggle split / unified view                     |
| `A`              | Toggle +/- annotations                          |
| `w`              | Toggle word wrap                                |
| `=` / `-`        | Show more / fewer context lines                 |
| `a`              | Toggle all lines vs the default context         |
| `s`              | Toggle the file sidebar                         |
| `t`              | Cycle colour themes                             |
| `q`              | Quit                                            |

## Development

```sh
make sync    # uv sync
make check   # ruff format --check, ruff check, ty check, pytest
```

Tooling: [uv](https://docs.astral.sh/uv/), [click](https://click.palletsprojects.com/),
[ruff](https://docs.astral.sh/ruff/), and [ty](https://github.com/astral-sh/ty).

## License

`textual-diff-view` is licensed under the AGPL-3.0; consult its repository for
the terms that apply to this project if you distribute it.
