"""Git plumbing backend.

This module wraps a small number of ``git`` commands to turn a pair of diff
targets (commit / index / working tree) into a list of :class:`FileChange`
entries and the raw blob contents for either side of each change.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from gdiff.model import ChangeStatus, FileChange


class GitError(RuntimeError):
    """Raised when a git command fails or the directory is not a repository."""


class TargetKind(StrEnum):
    COMMIT = "commit"
    INDEX = "index"
    WORKTREE = "worktree"


@dataclass(frozen=True, slots=True)
class Target:
    """One side of a diff."""

    kind: TargetKind
    ref: str | None = None

    @property
    def label(self) -> str:
        if self.kind is TargetKind.COMMIT:
            return self.ref or "?"
        return self.kind.value

    @classmethod
    def commit(cls, ref: str) -> Target:
        return cls(TargetKind.COMMIT, ref)

    @classmethod
    def index(cls) -> Target:
        return cls(TargetKind.INDEX)

    @classmethod
    def worktree(cls) -> Target:
        return cls(TargetKind.WORKTREE)


class GitRepo:
    """Thin wrapper around the ``git`` executable."""

    def __init__(self, path: str | Path = ".", *, git: str = "git") -> None:
        self.path = Path(path)
        self.git = git
        self._root: Path | None = None

    def _run(self, args: list[str], *, check: bool = True) -> bytes:
        try:
            proc = subprocess.run(
                [self.git, *args],
                cwd=self.path,
                capture_output=True,
            )
        except FileNotFoundError as error:  # pragma: no cover - environment specific
            raise GitError(f"`{self.git}` was not found on PATH") from error

        if check and proc.returncode != 0:
            message = proc.stderr.decode("utf-8", "replace").strip()
            raise GitError(message or f"git {' '.join(args)} failed")
        return proc.stdout

    @property
    def root(self) -> Path:
        """Absolute path to the repository top level."""
        if self._root is None:
            out = self._run(["rev-parse", "--show-toplevel"]).decode("utf-8", "replace").strip()
            if not out:
                raise GitError("not a git repository")
            self._root = Path(out)
        return self._root

    def is_repo(self) -> bool:
        try:
            _ = self.root
        except GitError:
            return False
        return True

    def resolve(self, rev: str) -> str:
        """Resolve a revision to a full commit hash."""
        out = self._run(["rev-parse", "--verify", f"{rev}^{{commit}}"]).decode("utf-8", "replace")
        return out.strip()

    def changes(
        self,
        left: Target,
        right: Target,
        *,
        paths: list[str] | None = None,
        find_renames: bool = True,
    ) -> list[FileChange]:
        """Enumerate changed files between two targets."""
        args = self._diff_args(left, right)
        args += ["-z", "--name-status"]
        args += ["-M"] if find_renames else ["--no-renames"]
        if paths:
            args += ["--", *paths]

        raw = self._run(args)

        # git diff-tree with a single commit and no --stdin behaves like
        # `git diff <commit>^..<commit>`; for our two-target usages we always
        # pass explicit revs or diff against the index/worktree, so that's fine.
        return _parse_name_status(raw)

    def _diff_args(self, left: Target, right: Target) -> list[str]:
        if left.kind is TargetKind.COMMIT and right.kind is TargetKind.COMMIT:
            return ["diff-tree", "-r", left.ref or "HEAD", right.ref or "HEAD"]
        if left.kind is TargetKind.COMMIT and right.kind is TargetKind.WORKTREE:
            return ["diff", left.ref or "HEAD"]
        if left.kind is TargetKind.INDEX and right.kind is TargetKind.WORKTREE:
            return ["diff"]
        if left.kind is TargetKind.COMMIT and right.kind is TargetKind.INDEX:
            return ["diff", "--cached", left.ref or "HEAD"]
        raise GitError(f"unsupported diff between {left.kind} and {right.kind}")

    def blob(self, target: Target, path: str | None) -> bytes:
        """Return the raw bytes of ``path`` on the given side of the diff.

        A missing path (or a path that does not exist on that side) yields
        ``b""`` so callers can treat adds/deletes uniformly.
        """
        if path is None:
            return b""
        if target.kind is TargetKind.WORKTREE:
            return self._worktree_bytes(path)
        spec = f":{path}" if target.kind is TargetKind.INDEX else f"{target.ref or 'HEAD'}:{path}"
        return self._run(["cat-file", "blob", spec], check=False)

    def _worktree_bytes(self, path: str) -> bytes:
        full = self.root / path
        try:
            if full.is_symlink():
                return os.readlink(full).encode("utf-8", "replace")
            return full.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            # Deleted files, submodule directories, or unreadable entries.
            return b""


def _parse_name_status(data: bytes) -> list[FileChange]:
    tokens = data.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()

    changes: list[FileChange] = []
    i = 0
    while i < len(tokens):
        raw_status = tokens[i].decode("ascii", "replace")
        i += 1
        code = raw_status[0].upper() if raw_status else "?"
        status = ChangeStatus.from_code(code)
        if status in (ChangeStatus.RENAMED, ChangeStatus.COPIED):
            old_path = _decode(tokens[i])
            new_path = _decode(tokens[i + 1])
            i += 2
            changes.append(FileChange(status, old_path, new_path))
        else:
            path = _decode(tokens[i])
            i += 1
            if status is ChangeStatus.ADDED:
                changes.append(FileChange(status, None, path))
            elif status is ChangeStatus.DELETED:
                changes.append(FileChange(status, path, None))
            else:
                changes.append(FileChange(status, path, path))
    return changes


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def is_binary(data: bytes) -> bool:
    """Heuristic binary detection, matching git's NUL-byte check."""
    return b"\0" in data[:8000]
