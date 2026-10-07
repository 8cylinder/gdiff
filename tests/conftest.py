from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def write(repo: Path, name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit(repo: Path, message: str = "commit") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    out = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    return out


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An initialized git repository with an initial commit."""
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")
    git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "README.md", "hello\n")
    commit(tmp_path, "initial")
    return tmp_path
