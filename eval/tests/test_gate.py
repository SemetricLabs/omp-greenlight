"""Gate-core tests with a stubbed client.

These cover the safety-critical decision logic without network access — the layer that
was silently broken by a bad refactor because nothing tested it.
"""

from __future__ import annotations

import pytest

from jev.answers import ChoiceAnswer, NoulAnswer, ScoreAnswer
from jev.client import Evaluation, Usage
from jev.gate import (
    DEFAULT_THRESHOLDS,
    PRESETS,
    Thresholds,
    build_state,
    classify,
)


class StubClient:
    """Returns a canned evaluation; records the states it was asked about."""

    def __init__(self, verdict: str, p_allow: float, severity: float, in_scope: float = 0.9) -> None:
        self.verdict = verdict
        self.p_allow = p_allow
        self.severity = severity
        self.in_scope = in_scope
        self.states: list[str] = []

    def evaluate(self, state, questions):  # noqa: ANN001 - mirrors the client protocol
        self.states.append(state)
        return Evaluation(
            model="jev-test",
            answers={
                "verdict": ChoiceAnswer(
                    choice=self.verdict,
                    probabilities={"allow": self.p_allow, "review": 1 - self.p_allow, "deny": 0.0},
                    confidence=0.9,
                ),
                "severity": ScoreAnswer(
                    score=self.severity,
                    legend={"0": "none", "1": "low", "2": "hard", "3": "irreversible"},
                    probabilities={"0": 1.0},
                    confidence=0.9,
                ),
                "in_scope": NoulAnswer(noul=self.in_scope),
            },
            usage=Usage(input_tokens=100, output_tokens=10),
            latency_ms=12.0,
        )


def test_default_threshold_auto_approves_a_confident_allow() -> None:
    verdict = classify(StubClient("allow", 0.97, 0.1), tool="bash", args={"command": "ls"}, task="t", cwd="/tmp")
    assert verdict.can_auto_approve


def test_probability_below_the_bar_escalates() -> None:
    verdict = classify(StubClient("allow", 0.85, 0.1), tool="bash", args={"command": "x"}, task="t", cwd="/tmp")
    assert not verdict.can_auto_approve


def test_severity_ceiling_blocks_even_at_high_probability() -> None:
    verdict = classify(StubClient("allow", 0.99, 2.5), tool="bash", args={"command": "x"}, task="t", cwd="/tmp")
    assert not verdict.can_auto_approve


def test_non_allow_verdicts_never_auto_approve() -> None:
    for choice in ("review", "deny"):
        verdict = classify(StubClient(choice, 0.99, 0.0), tool="bash", args={"command": "x"}, task="t", cwd="/tmp")
        assert not verdict.can_auto_approve


def test_operator_threshold_is_honoured() -> None:
    client = StubClient("allow", 0.82, 0.1)
    strict = classify(client, tool="bash", args={"command": "x"}, task="t", cwd="/tmp", thresholds=PRESETS["default"])
    loose = classify(client, tool="bash", args={"command": "x"}, task="t", cwd="/tmp", thresholds=PRESETS["permissive"])
    assert not strict.can_auto_approve
    assert loose.can_auto_approve
    assert loose.thresholds.name == "permissive"


def test_unknown_verdict_raises_rather_than_defaulting_to_allow() -> None:
    with pytest.raises(ValueError):
        classify(StubClient("maybe", 0.99, 0.0), tool="bash", args={"command": "x"}, task="t", cwd="/tmp")


def test_thresholds_reach_the_returned_verdict() -> None:
    custom = Thresholds(min_p=0.5, severity_ceiling=3.0, name="custom")
    verdict = classify(StubClient("allow", 0.6, 0.2), tool="bash", args={"command": "x"}, task="t", cwd="/tmp", thresholds=custom)
    assert verdict.thresholds is custom
    assert verdict.can_auto_approve


def test_build_state_carries_task_and_call() -> None:
    state = build_state("bash", {"command": "rm -rf /"}, "free disk space", "/tmp")
    assert "free disk space" in state
    assert "rm -rf /" in state
    assert "/tmp" in state


def test_default_preset_is_the_documented_operating_point() -> None:
    assert (DEFAULT_THRESHOLDS.min_p, DEFAULT_THRESHOLDS.severity_ceiling) == (0.90, 2.0)


def test_history_window_reaches_the_state() -> None:
    history = [
        {"tool": "bash", "args": "command=git status", "error": False},
        {"tool": "bash", "args": "command=pytest -q", "error": True},
    ]
    state = build_state("bash", {"command": "rm -rf ./dist"}, "clean the build", "/repo", history)
    assert "Recent tool calls in this session" in state
    assert "git status" in state
    assert "[last attempt errored]" in state


def test_no_history_means_no_history_block() -> None:
    assert "Recent tool calls" not in build_state("bash", {"command": "ls"}, "t", "/tmp")
    assert "Recent tool calls" not in build_state("bash", {"command": "ls"}, "t", "/tmp", [])
