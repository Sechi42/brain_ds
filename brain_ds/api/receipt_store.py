from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionReceipt:
    timestamp: str
    tool: str
    params_summary: str
    status: str
    graph_id: str
    target_id: str | None = None


class ReceiptStore:
    def __init__(self, max_receipts: int = 50) -> None:
        self._receipts: deque[ActionReceipt] = deque(maxlen=max_receipts)

    def add(self, receipt: ActionReceipt) -> None:
        self._receipts.append(receipt)

    def list(self) -> list[ActionReceipt]:
        return list(reversed(self._receipts))
