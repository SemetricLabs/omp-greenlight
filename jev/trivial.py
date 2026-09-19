"""Tier-1 trivial fast path.

Strictly literal, whole-command, read-only commands that are allowed to run with
no Jev call and no human prompt. A false positive here is a *silent execution*
bug, so the matcher refuses anything containing shell syntax at all and matches
the whole command, never a prefix.

Anything not matched here goes to Jev (tier 2).
"""

from __future__ import annotations

import re
from typing import Mapping

# Any of these means the command is more than a literal argv: reject outright.
# Notably includes quotes, globs, expansion, redirection, chaining, newlines.
_SHELL_SYNTAX = re.compile(r"""[\s\S]*[|&;<>$`\\(){}\[\]*?!#~'"]|[\s\S]*\n""")

_PATTERNS = (
    re.compile(r"ls(?: +-[a-zA-Z]+)*(?: +[\w./@+-]+)*"),
    re.compile(r"pwd"),
    re.compile(r"git +(?:status|log|diff|show|branch)(?: +[\w./@=^-]+)*"),
    re.compile(r"which +[\w./+-]+"),
    re.compile(r"wc +-l +[\w./@+-]+(?: +[\w./@+-]+)*"),
)

# `cat` is deliberately absent: it reads .env, credentials, private keys.
TRIVIAL_TOOLS = frozenset({"bash"})


def is_trivial(tool: str, args: Mapping[str, object]) -> bool:
    """True only for a whole-command literal read-only invocation."""
    if tool not in TRIVIAL_TOOLS:
        return False
    command = args.get("command")
    if not isinstance(command, str):
        return False
    command = command.strip()
    if not command or _SHELL_SYNTAX.match(command):
        return False
    return any(pattern.fullmatch(command) for pattern in _PATTERNS)
