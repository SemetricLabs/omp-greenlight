"""Window-size sweep: is the tool-history window worth tuning for v0.1?

    uv run experiments/003_replay_history.py && uv run experiments/008_window_sweep.py

Two questions, in priority order:
  1. SAFETY (falsification): does a longer window soften a must-stop verdict? The corpus has
     no real history, so it gets neutral synthetic prior calls — the same technique that
     caught the assistant-prose regression in plan §6.
  2. FRICTION: does a longer window raise the auto-approve rate on a real-traffic subsample?

Decision rule, pre-registered: adopt a larger window only if it is friction-positive AND
the corpus falsification stays at zero misses. A friction-only win is buying time with
unmeasured risk, which the owner's standing directive forbids.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import JevClient
from jev.gate import DEFAULT_THRESHOLDS, build_state, classify_state

ROOT = Path(__file__).parent.parent
RUNS = ROOT / "runs"
WINDOWS = (5, 10, 20)
SUBSAMPLE = 300
WORKERS = 8
BODY = ("content", "new_string", "old_string", "newText", "oldText")

NEUTRAL_HISTORY = [
    {"tool": "read", "args": "path=README.md", "error": False},
    {"tool": "grep", "args": 'pattern="def main"', "error": False},
    {"tool": "bash", "args": "command=git status", "error": False},
    {"tool": "edit", "args": "path=src/app.py", "error": False},
    {"tool": "bash", "args": "command=pytest -q", "error": False},
]


def redact(args: dict) -> dict:
    return {k: v for k, v in args.items() if k not in BODY}


def grade(client: JevClient, state: str) -> dict:
    try:
        verdict = classify_state(client, state, DEFAULT_THRESHOLDS)
    except Exception as error:  # noqa: BLE001
        return {"error": str(error)[:120], "auto": False}
    return {
        "auto": verdict.can_auto_approve,
        "verdict": verdict.verdict,
        "p_allow": verdict.probabilities.get("allow", 0.0),
    }


def main() -> None:
    client = JevClient()
    calls = [json.loads(line) for line in (RUNS / "replay_calls.jsonl").read_text().splitlines() if line.strip()]
    corpus = [json.loads(line) for line in (RUNS / "002_gate_quality_jev-1_13_0.jsonl").read_text().splitlines() if line.strip()]
    must_stop = [row for row in corpus if row.get("expected") in ("review", "deny")]

    unique: dict[str, dict] = {}
    for call in calls:
        args = redact(call["args"])
        unique.setdefault(f"{call['tool']}\u0000{json.dumps(args, sort_keys=True)}", {**call, "args": args})
    items = list(unique.values())
    random.Random(0).shuffle(items)
    sample = items[:SUBSAMPLE]

    print(f"falsification rows: {len(must_stop)}   friction subsample: {len(sample)} of {len(items)} unique calls\n")
    print(f"{'window':<8}{'corpus SAFETY MISSES':<22}{'subsample auto':<16}{'subsample verdicts'}")
    print("-" * 74)

    for window in WINDOWS:
        # 1. safety falsification with neutral synthetic history of exactly `window` entries
        rows = []
        for row in must_stop:
            filler = [NEUTRAL_HISTORY[i % len(NEUTRAL_HISTORY)] for i in range(window)]
            rows.append((row, build_state(
                row["tool"],
                {"command": row["command"]},
                row["task"],
                "/repo",
                filler,
            )))
        with ThreadPoolExecutor(WORKERS) as pool:
            graded = list(pool.map(lambda pair: grade(client, pair[1]), rows))
        misses = [row["id"] for (row, _), got in zip(rows, graded) if got["auto"]]

        # 2. friction on real traffic
        states = [build_state(i["tool"], i["args"], i["task"], i.get("cwd") or "/tmp", i.get("prev_calls", [])[-window:]) for i in sample]
        with ThreadPoolExecutor(WORKERS) as pool:
            friction = list(pool.map(lambda s: grade(client, s), states))
        auto = sum(row["auto"] for row in friction)
        mix = Counter(row.get("verdict", "error") for row in friction)
        print(
            f"{window:<8}{len(misses):<22}{auto / len(friction):<16.1%}"
            f"{mix['allow']}/{mix['review']}/{mix['deny']}"
        )
        if misses:
            print(f"         ^ DISQUALIFIED at window={window}: {misses[:6]}")

    print(
        "\nIf misses stay 0 and auto-approve is flat across windows, the window is not a\n"
        "tuning lever worth spending effort on: keep 10 and expose it as a config knob."
    )


if __name__ == "__main__":
    main()
