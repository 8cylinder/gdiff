# gdiff

A terminal UI replacement for `git diff`, built with
[Textual](https://github.com/textualize/textual) and
[textual-diff-view](https://github.com/batrachianai/textual-diff-view).

`gdiff` resolves revisions with git plumbing and renders each changed file in a
side-by-side or unified diff view.

## Install

```sh
uv sync            # development
uv run gdiff       # run from the checkout
# or install the CLI:
uv tool install .
```

## Usage

```sh
gdiff                       # working tree vs index (like `git diff`)
gdiff HEAD                  # HEAD vs working tree
gdiff main feature          # two commits
gdiff --staged              # index vs HEAD
gdiff HEAD~1 HEAD -- src/   # limit to a pathspec
```

When stdout is not a terminal (a pipe or redirect), `gdiff` delegates to
`git diff` so it stays scriptable.

### Keys

| Key     | Action                    |
| ------- | ------------------------- |
| `n`/`p` | Next / previous file      |
| `space` | Toggle split / unified    |
| `a`     | Toggle +/- annotations    |
| `w`     | Toggle word wrap          |
| `q`     | Quit                      |

## Development

```sh
make check   # ruff format --check, ruff check, ty check, pytest
```

Tooling: [uv](https://docs.astral.sh/uv/), [ruff](https://docs.astral.sh/ruff/),
and [ty](https://github.com/astral-sh/ty).

## License

`textual-diff-view` is licensed under the AGPL-3.0; consult its repository for
the terms that apply to this project if you distribute it.
