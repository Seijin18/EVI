# /home/marshibs/Projects/EVI/agent/memory.py
from collections import deque
from typing import Any, Callable


class BoundedMemory:
    """Keeps only the last N message pairs to cap RAM usage.

    One instance belongs to one `session_id` — see `services/session_memory.py`.
    """

    def __init__(self, max_pairs: int = 8, *, session_id: str = ""):
        # 8 pairs = 16 messages max
        self.max_pairs = max_pairs
        self.session_id = session_id
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
        """Empty the buffer and drop any trim callback.

        The callback captures a session_id by closure; leaving it bound across a
        clear() made it fire for whichever session reused the buffer next.
        """
        self.buffer.clear()
        self._on_trim = None

    def pair_count(self) -> int:
        return len(self.buffer) // 2
