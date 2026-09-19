"""Replay real tool calls through the three tiers.

    uv run experiments/003_replay_history.py && uv run experiments/004_replay_gate.py

Answers the question the corpus cannot: on this machine's actual traffic, how many
prompts would the gate raise per hour of work, and how much of it would skip the
model entirely.

Privacy: `write` / `edit` / `apply_patch` bodies are NOT sent. Only the path is
graded — per the plan's rule that no file contents leave the host during the trial.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import JevClient, JevError
from jev.gate import classify
from jev.trivial import is_trivial

ROOT = Path(__file__).parent.parent
CALLS = ROOT / "runs" / "replay_calls.jsonl"
OUT = ROOT / "runs" / "replay_verdicts.jsonl"
WORKERS = 8
BODY_KEYS = {"content", "new_string", "old_string", "newText", "oldText"}


def redact(tool: str, args: dict) -> dict:
    """Drop file bodies; keep the shape the gate actually needs."""
    if tool in ("write", "edit", "apply_patch"):
        return {k: v for k, v in args.items() if k not in BODY_KEYS}
    return args


def key_of(tool: str, args: dict) -> str:
    return f"{tool}\u0000{json.dumps(args, sort_keys=True)}"


def parse_ts(value: object) -> float | None:
    """Session entries carry ISO-8601 strings, not epoch millis."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
        except ValueError:
            return None
    return None


def main() -> None:
    calls = [json.loads(line) for line in CALLS.read_text().splitlines() if line.strip()]
    unique: dict[str, dict] = {}
    for call in calls:
        args = redact(call["tool"], call["args"])
        unique.setdefault(key_of(call["tool"], args), {**call, "args": args})
    print(f"calls {len(calls)}, unique {len(unique)}")

    client = JevClient()

    def judge(item: dict) -> dict:
        tool, args, task = item["tool"], item["args"], item["task"]
        if is_trivial(tool, args):
            return {**item, "tier": "trivial", "auto": True}
        try:
            verdict = classify(client, tool=tool, args=args, task=task, cwd=item.get("cwd") or "/tmp", history=item.get("prev_calls"))
        except (JevError, ValueError) as error:
            return {**item, "tier": "jev", "error": str(error)[:200], "auto": False, "escalated": True}
        return {
            **item,
            "tier": "jev",
            "verdict": verdict.verdict,
            "p_allow": round(verdict.probabilities.get("allow", 0.0), 4),
            "severity": round(verdict.severity, 3),
            "in_scope": round(verdict.in_scope, 3),
            "auto": verdict.can_auto_approve,
            "escalated": not verdict.can_auto_approve,
            "latency_ms": round(verdict.latency_ms, 1),
        }

    items = list(unique.values())
    with ThreadPoolExecutor(WORKERS) as pool:
        judged = list(pool.map(judge, items))

    # session-hours: how long the replayed sessions actually ran
    spans: dict[str, list[float]] = {}
    for call in calls:
        stamp = parse_ts(call["ts"])
        if stamp is not None:
            spans.setdefault(call["session"], []).append(stamp)
    hours = sum((max(v) - min(v)) / 3_600_000 for v in spans.values() if len(v) > 1)

    # weight back to real frequency so prompt-rate reflects real traffic, not unique commands
    freq = Counter(key_of(c["tool"], redact(c["tool"], c["args"])) for c in calls)
    escalations = sum(
        freq[key_of(j["tool"], j["args"])] for j in judged if j.get("escalated")
    )
    autos = sum(freq[key_of(j["tool"], j["args"])] for j in judged if j.get("auto"))

    by_tool = Counter(c["tool"] for c in calls)
    auto_by_tool = Counter(
        j["tool"] for j in judged if j.get("auto") for _ in range(freq[key_of(j["tool"], j["args"])])
    )
    latencies = sorted(j["latency_ms"] for j in judged if "latency_ms" in j)

    print(json.dumps({
        "real_calls": len(calls),
        "unique_calls_judged": len(judged),
        "sessions": len(spans),
        "session_hours": round(hours, 2),
        "auto_approved": autos,
        "escalated": escalations,
        "auto_rate": round(autos / len(calls), 3),
        "escalation_rate": round(escalations / len(calls), 3),
        "prompts_per_hour": round(escalations / hours, 1) if hours else None,
        "errors": sum(1 for j in judged if "error" in j),
        "tier1_unique": sum(1 for j in judged if j["tier"] == "trivial"),
        "by_tool": dict(by_tool),
        "auto_by_tool": dict(auto_by_tool),
        "verdict_mix_unique": dict(Counter(j.get("verdict", j["tier"]) for j in judged)),
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": latencies[int(len(latencies) * 0.95) - 1] if latencies else None,
    }, indent=2))

    print("\ntop escalated commands by real frequency:")
    ranked = sorted(
        (j for j in judged if j.get("escalated")),
        key=lambda j: -freq[key_of(j["tool"], j["args"])],
    )[:20]
    for j in ranked:
        text = j["args"].get("command") or j["args"].get("path") or j["args"].get("file_path") or ""
        print(f"  x{freq[key_of(j['tool'], j['args'])]:<3} {j['tool']:<6} {j.get('verdict','error'):<7} "
              f"P={j.get('p_allow')} sev={j.get('severity')} :: {str(text)[:70]}")

    OUT.write_text("\n".join(json.dumps(j) for j in judged))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
