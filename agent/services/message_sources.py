"""Message source adapters for WhatsApp (and similar) pipelines."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List


@dataclass
class IncomingMessage:
    id: str
    sender: str
    text: str
    ts: str  # ISO-8601
    from_me: bool = False
    is_group: bool = False
    label: str = ""  # pushName or chat display name


class MessageSource(ABC):
    @abstractmethod
    def iter_messages(self) -> Iterator[IncomingMessage]:
        pass


class FixtureMessageSource(MessageSource):
    """Reads tests/fixtures/whatsapp/messages.jsonl (one JSON object per line)."""

    def __init__(self, path: Path):
        self.path = path

    def iter_messages(self) -> Iterator[IncomingMessage]:
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                yield IncomingMessage(
                    id=row["id"],
                    sender=row.get("from", row.get("sender", "unknown")),
                    text=row["text"],
                    ts=row["ts"],
                )


class EvolutionMessageSource(MessageSource):
    """In-memory messages from a parsed Evolution API webhook body."""

    def __init__(self, messages: List[IncomingMessage]):
        self._messages = messages

    def iter_messages(self) -> Iterator[IncomingMessage]:
        yield from self._messages


def load_messages(
    source: str,
    fixture_path: Path | None = None,
    evolution_body: dict | None = None,
) -> List[IncomingMessage]:
    if source == "fixture":
        if not fixture_path or not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")
        return list(FixtureMessageSource(fixture_path).iter_messages())
    if source == "evolution":
        from services.evolution_parser import parse_evolution_webhook

        if not evolution_body:
            raise ValueError("evolution_body required for source=evolution")
        return parse_evolution_webhook(evolution_body)
    if source == "live":
        raise NotImplementedError(
            "Use source=evolution with webhook payload or source=fixture for dev."
        )
    raise ValueError(f"Unknown message source: {source}")
