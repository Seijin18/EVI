# /home/marshibs/Projects/EVI/agent/memory.py
from collections import deque
from typing import Any, Callable


class BoundedMemory:
    """Keeps only the last N message pairs to cap RAM usage."""

    def __init__(self, max_pairs: int = 8):
        # 8 pairs = 16 messages max
        self.max_pairs = max_pairs
        self.buffer: deque = deque(maxlen=max_pairs * 2)
        self._on_trim: Callable[[], None] | None = None

    def set_on_trim(self, callback: Callable[[], None] | None) -> None:
        self._on_trim = callback

    def add(self, message: Any):
        at_capacity = len(self.buffer) >= self.buffer.maxlen
        if at_capacity and self._on_trim:
            self._on_trim()
        self.buffer.append(message)

    def get_messages(self) -> list:
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()

    def pair_count(self) -> int:
        return len(self.buffer) // 2
