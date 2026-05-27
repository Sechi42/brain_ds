from __future__ import annotations

import unittest

from brain_ds.api.receipt_store import ActionReceipt, ReceiptStore


class ReceiptStoreTests(unittest.TestCase):
    def test_add_51_receipts_keeps_newest_50_and_evicts_oldest(self) -> None:
        store = ReceiptStore(max_receipts=50)

        for i in range(51):
            store.add(
                ActionReceipt(
                    timestamp=f"2026-01-01T00:00:{i:02d}Z",
                    tool="update_node",
                    params_summary=f"node=n-{i}",
                    status="ok",
                    graph_id="g-1",
                    target_id=f"n-{i}",
                )
            )

        receipts = store.list()
        self.assertEqual(len(receipts), 50)
        self.assertEqual(receipts[0].target_id, "n-50")
        self.assertEqual(receipts[-1].target_id, "n-1")


if __name__ == "__main__":
    unittest.main()
