"""Typed answers returned by Jev.

Each answer's `type` matches its question's `type`. Parsing is strict: an
unrecognized answer type or a missing field raises rather than silently
producing a half-populated object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class InvalidAnswer(ValueError):
    """A response body that does not match the documented answer shapes."""


@dataclass(frozen=True, slots=True)
class NoulAnswer:
    """Yes/no answer: probability the answer is yes, 0..1. Carries no confidence."""

    noul: float

    type = "noul"


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    """Chosen option, its full distribution, and the derived confidence."""

    choice: str
    probabilities: Mapping[str, float]
    confidence: float

    type = "choice"

    def p(self, option: str) -> float:
        """Probability mass on `option`; 0.0 for an option outside the criteria."""
        return float(self.probabilities.get(option, 0.0))


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    """Probability-weighted level index, the level legend, and the distribution."""

    score: float
    legend: Mapping[str, str]
    probabilities: Mapping[str, float]
    confidence: float

    type = "score"

    def p(self, level: int) -> float:
        """Probability mass on level index `level`."""
        return float(self.probabilities.get(str(level), 0.0))


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


def parse_answers(raw: Mapping[str, Any]) -> dict[str, Answer]:
    """Parse the `answers` object, keyed by the question ids we sent."""
    answers: dict[str, Answer] = {}
    for key, body in raw.items():
        answers[key] = _parse_answer(key, body)
    return answers


def _parse_answer(key: str, body: Any) -> Answer:
    if not isinstance(body, Mapping):
        raise InvalidAnswer(f"answer {key!r}: expected an object, got {type(body).__name__}")
    kind = body.get("type")
    try:
        match kind:
            case "noul":
                return NoulAnswer(noul=float(body["noul"]))
            case "choice":
                return ChoiceAnswer(
                    choice=str(body["choice"]),
                    probabilities=_floats(key, body["probabilities"]),
                    confidence=float(body["confidence"]),
                )
            case "score":
                return ScoreAnswer(
                    score=float(body["score"]),
                    legend={str(k): str(v) for k, v in body["legend"].items()},
                    probabilities=_floats(key, body["probabilities"]),
                    confidence=float(body["confidence"]),
                )
    except KeyError as exc:
        raise InvalidAnswer(f"answer {key!r} ({kind}): missing field {exc.args[0]!r}") from exc
    raise InvalidAnswer(f"answer {key!r}: unknown type {kind!r}")


def _floats(key: str, raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise InvalidAnswer(f"answer {key!r}: probabilities must be an object")
    return {str(k): float(v) for k, v in raw.items()}
