"""Extract real gated tool calls from OMP session history, with context.

    uv run experiments/003_replay_history.py

Reads `~/.omp/agent/sessions/**/*.jsonl` (local only — no network) and emits one record
per gated tool call plus the context the gate could be given:

- `task`          the last user prompt before the call (what the baseline passes)
- `title`         the session's auto-title
- `recent_user`   the last 3 user messages, trimmed
- `last_assistant` the last assistant text before the call, trimmed
- `prev_calls`    the preceding ≤10 tool calls in the session, with args summary + outcome

Role names are camelCase in persisted entries (`assistant`, `user`, `toolResult`) and the
block type is `toolCall`. A snake_case filter silently matches nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SESSIONS = Path.home() / ".omp" / "agent" / "sessions"
OUT = Path(__file__).parent.parent / "runs" / "replay_calls.jsonl"
GATED = {"bash", "eval", "write", "edit", "apply_patch", "delete", "move"}
WINDOW = 20  # extract more than the shipping window so window sizes can be compared
BODY_KEYS = ("content", "new_string", "old_string", "newText", "oldText")


def text_of_blocks(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") in ("text", "input_text")
    ]
    return "\n".join(part for part in parts if part).strip()


def summarize_args(tool: str, args: Any) -> str:
    """One line, bodies removed — the history window must not carry file contents."""
    if not isinstance(args, dict):
        return ""
    kept = {k: v for k, v in args.items() if k not in BODY_KEYS}
    for key in ("command", "path", "file_path", "dst"):
        if isinstance(kept.get(key), str):
            return f"{key}={kept[key][:200]}"
    return json.dumps(kept)[:200]


def extract_file(path: Path, session: str) -> list[dict]:
    entries: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    outcomes: dict[str, bool] = {}
    for entry in entries:
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if isinstance(message, dict) and message.get("role") == "toolResult":
            call_id = message.get("toolCallId")
            if isinstance(call_id, str):
                outcomes[call_id] = bool(message.get("isError"))

    cwd = ""
    title = ""
    for entry in entries:
        if entry.get("type") == "session":
            cwd = str(entry.get("cwd") or "")
            title = str(entry.get("title") or "")
            break

    records: list[dict] = []
    recent_user: list[str] = []
    last_assistant = ""
    history: list[dict] = []

    for entry in entries:
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")

        if role == "user":
            text = text_of_blocks(message.get("content"))
            if text:
                recent_user.append(text[:2000])
                recent_user = recent_user[-3:]
            continue
        if role != "assistant":
            continue

        text = text_of_blocks(message.get("content"))
        if text:
            last_assistant = text[:1200]

        for block in message.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            name = str(block.get("name"))
            args = block.get("arguments") or {}
            call_id = block.get("id")
            if name in GATED:
                records.append(
                    {
                        "session": session,
                        "ts": entry.get("timestamp"),
                        "cwd": cwd,
                        "title": title,
                        "tool": name,
                        "args": args,
                        "task": recent_user[-1][:2000] if recent_user else "",
                        "recent_user": list(recent_user),
                        "last_assistant": last_assistant,
                        "prev_calls": list(history[-WINDOW:]),
                    }
                )
            history.append(
                {
                    "tool": name,
                    "args": summarize_args(name, args),
                    "error": outcomes.get(call_id, False) if isinstance(call_id, str) else None,
                }
            )
    return records


def main() -> None:
    records: list[dict] = []
    for path in sorted(SESSIONS.glob("**/*.jsonl")):
        records.extend(extract_file(path, path.parent.name))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r) for r in records))

    by_tool: dict[str, int] = {}
    for record in records:
        by_tool[record["tool"]] = by_tool.get(record["tool"], 0) + 1
    print(json.dumps({
        "calls": len(records),
        "sessions": len({r["session"] for r in records}),
        "with_task": sum(1 for r in records if r["task"]),
        "with_title": sum(1 for r in records if r["title"]),
        "with_history": sum(1 for r in records if r["prev_calls"]),
        "with_last_assistant": sum(1 for r in records if r["last_assistant"]),
        "avg_history_len": round(sum(len(r["prev_calls"]) for r in records) / max(len(records), 1), 1),
        "by_tool": by_tool,
        "out": str(OUT),
    }, indent=2))


if __name__ == "__main__":
    main()
