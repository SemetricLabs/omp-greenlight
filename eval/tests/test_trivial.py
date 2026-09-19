"""Tier-1 trivial matcher: the negative cases are the point.

A false positive is silent execution, so every shell-syntax shape that could hide
a side effect behind a read-only-looking prefix must fail.
"""

from __future__ import annotations

import pytest

from jev.trivial import is_trivial


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "ls -la",
        "ls -la src/",
        "ls -l /home/dev/Documents/dev",
        "pwd",
        "git status",
        "git status --short",
        "git log --oneline -20",
        "git diff HEAD",
        "git show 3bc7901",
        "git branch -a",
        "which python3",
        "wc -l README.md",
    ],
)
def test_trivial_allows_plain_read_only(command: str) -> None:
    assert is_trivial("bash", {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        # chaining and sequencing
        "ls; rm -rf x",
        "ls && rm -rf x",
        "ls || rm -rf x",
        # redirection
        "ls > f",
        "ls >> f",
        "git status < in",
        # substitution and expansion
        "ls $(rm x)",
        "ls `rm x`",
        "ls $HOME",
        "ls ${HOME}",
        # globs, braces, quotes
        "ls *",
        "ls ?",
        "ls {a,b}",
        'ls "src dir"',
        "ls 'src dir'",
        # other verbs that are not read-only or not on the list
        "git push",
        "git checkout -- .",
        "git reset --hard",
        "cat .env",
        "echo hi",
        "rm -rf ./dist",
        "sudo ls",
        "ls | sh",
        "ls #comment",
        "ls\nrm -rf x",
        # empty / malformed
        "",
        "   ",
    ],
)
def test_trivial_rejects_anything_with_shell_syntax(command: str) -> None:
    assert not is_trivial("bash", {"command": command})


def test_trivial_rejects_non_bash_tools() -> None:
    assert not is_trivial("eval", {"command": "ls"})
    assert not is_trivial("write", {"command": "ls"})


def test_trivial_rejects_missing_or_non_string_command() -> None:
    assert not is_trivial("bash", {})
    assert not is_trivial("bash", {"command": None})
    assert not is_trivial("bash", {"command": ["ls"]})
