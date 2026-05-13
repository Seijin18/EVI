# /home/marshibs/Projects/EVI/agent/memory.py
from collections import deque
from langchain_core.messages import BaseMessage


class BoundedMemory:
    """Keeps only the last N message pairs to cap RAM usage."""

    def __init__(self, max_pairs: int = 8):
        # 8 pairs = 16 messages max
        self.buffer: deque = deque(maxlen=max_pairs * 2)

    def add(self, message: BaseMessage):
        self.buffer.append(message)

    def get_messages(self) -> list:
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()
