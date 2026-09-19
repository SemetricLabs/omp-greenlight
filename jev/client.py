"""Zero-dependency client for the TypeSafe System One (Jev) endpoint.

One POST, stdlib only. Retries 429/529 with exponential backoff, as the API
reference instructs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .answers import (
    Answer,
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    parse_answers,
)
from .questions import Question, questions_json

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
RETRY_STATUS = (429, 529)
State = str | Mapping[str, Any] | Sequence[Any]


class JevError(RuntimeError):
    """Transport failure, API error, or a response we could not parse."""


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class Evaluation:
    """One evaluation: what the model was asked, and what it answered."""

    model: str
    answers: Mapping[str, Answer]
    usage: Usage
    latency_ms: float

    def answer(self, question_id: str) -> Answer:
        try:
            return self.answers[question_id]
        except KeyError:
            raise JevError(
                f"no answer for {question_id!r}; got {sorted(self.answers)}"
            ) from None

    def noul(self, question_id: str) -> float:
        """Probability the answer to `question_id` is yes."""
        return self._typed(question_id, NoulAnswer).noul

    def choice(self, question_id: str) -> str:
        """Highest-probability option for `question_id`."""
        return self._typed(question_id, ChoiceAnswer).choice

    def score(self, question_id: str) -> float:
        """Probability-weighted level index for `question_id`."""
        return self._typed(question_id, ScoreAnswer).score

    def _typed(self, question_id: str, kind: type) -> Any:
        answer = self.answer(question_id)
        if not isinstance(answer, kind):
            raise TypeError(
                f"{question_id!r} is a {type(answer).__name__}, not a {kind.__name__}"
            )
        return answer


class JevClient:
    """Minimal client for `POST /v1/systemone`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        url: str = API_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        max_attempts: int = 4,
        backoff: float = 0.5,
    ) -> None:
        key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise JevError(
                "no API key: pass api_key= or set TYPESAFE_API_KEY "
                "(dashboard: https://console.typesafe.ai/settings/keys)"
            )
        self._key = key
        self.url = url
        self.model = model
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.backoff = backoff

    def evaluate(
        self,
        state: State,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
    ) -> Evaluation:
        """Evaluate `state` against `questions`; answers keep the question ids."""
        body = {
            "state": state,
            "model": model or self.model,
            "questions": questions_json(questions),
        }
        payload, latency_ms = self._post(body)
        try:
            answers = parse_answers(payload["answers"])
            usage = Usage(
                input_tokens=int(payload["usage"]["input_tokens"]),
                output_tokens=int(payload["usage"]["output_tokens"]),
            )
            resolved_model = str(payload["model"])
        except KeyError as exc:
            raise JevError(f"response missing field {exc.args[0]!r}: {payload!r}") from exc
        return Evaluation(
            model=resolved_model,
            answers=answers,
            usage=usage,
            latency_ms=latency_ms,
        )

    def _post(self, body: Mapping[str, Any]) -> tuple[dict[str, Any], float]:
        data = json.dumps(body).encode()
        attempt = 0
        while True:
            attempt += 1
            request = urllib.request.Request(
                self.url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read())
                    return payload, (time.perf_counter() - started) * 1000
            except urllib.error.HTTPError as exc:
                detail = _error_detail(exc)
                if exc.code not in RETRY_STATUS or attempt >= self.max_attempts:
                    raise JevError(f"HTTP {exc.code}: {detail}") from exc
                delay = _retry_delay(exc, self.backoff, attempt)
            except urllib.error.URLError as exc:
                if attempt >= self.max_attempts:
                    raise JevError(f"request failed: {exc.reason}") from exc
                delay = self.backoff * 2 ** (attempt - 1)
            time.sleep(delay)


def _error_detail(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode("utf-8", "replace").strip()
    return raw or exc.reason or "no body"


def _retry_delay(exc: urllib.error.HTTPError, backoff: float, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return backoff * 2 ** (attempt - 1)
