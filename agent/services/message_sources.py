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


class LiveMessageSource(MessageSource):
    """Placeholder for future webhook/API integration."""

    def iter_messages(self) -> Iterator[IncomingMessage]:
        raise NotImplementedError(
            "Live WhatsApp adapter not configured. Use fixture source for development."
        )


def load_messages(source: str, fixture_path: Path | None = None) -> List[IncomingMessage]:
    if source == "fixture":
        if not fixture_path or not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")
        return list(FixtureMessageSource(fixture_path).iter_messages())
    if source == "live":
        return list(LiveMessageSource().iter_messages())
    raise ValueError(f"Unknown message source: {source}")
