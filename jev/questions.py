"""Typed question builders for the TypeSafe /v1/systemone endpoint.

Three question types exist; every one carries `instructions` and adds its own
`criteria`. Builders validate locally so malformed questions fail here with a
clear message instead of as a 422 from the API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Sequence


class InvalidQuestion(ValueError):
    """A question that cannot be sent: the API would reject it."""


class Question(ABC):
    """One typed question. Subclasses are the only accepted question values."""

    type: ClassVar[str]

    @abstractmethod
    def to_json(self) -> dict[str, Any]:
        """Request payload for this question."""


@dataclass(frozen=True, slots=True)
class Noul(Question):
    """Yes/no question. Answers as the probability the answer is yes."""

    instructions: str
    true: str | None = None
    false: str | None = None

    type: ClassVar[str] = "noul"

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        criteria = {"true": self.true, "false": self.false}
        criteria = {k: v for k, v in criteria.items() if v is not None}
        if criteria:
            payload["criteria"] = criteria
        return payload


@dataclass(frozen=True, slots=True)
class Choice(Question):
    """Pick one option. Answers as the argmax option plus the whole distribution."""

    instructions: str
    criteria: Mapping[str, str | None]

    type: ClassVar[str] = "choice"

    def __post_init__(self) -> None:
        if len(self.criteria) < 2:
            raise InvalidQuestion(
                f"choice needs at least 2 options, got {len(self.criteria)}"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": dict(self.criteria),
        }


@dataclass(frozen=True, slots=True)
class Score(Question):
    """Rate along ordered levels. Answers as a probability-weighted level index."""

    instructions: str
    criteria: Sequence[str]

    type: ClassVar[str] = "score"

    def __post_init__(self) -> None:
        if len(self.criteria) < 2:
            raise InvalidQuestion(
                f"score needs at least 2 levels, got {len(self.criteria)}"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": list(self.criteria),
        }


def questions_json(questions: Mapping[str, Question]) -> dict[str, Any]:
    """Serialize a question map, rejecting anything that is not a Question."""
    if not questions:
        raise InvalidQuestion("at least one question is required")
    payload: dict[str, Any] = {}
    for key, question in questions.items():
        if not isinstance(question, Question):
            raise TypeError(
                f"question {key!r} must be a Noul/Choice/Score, got {type(question).__name__}"
            )
        payload[key] = question.to_json()
    return payload
