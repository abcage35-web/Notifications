import contextlib
import io
import os
import unittest
from datetime import date
from unittest import mock

import send_pachca_report as sender
import build_action_report as actions


class StockSnapshotGuardTest(unittest.TestCase):
    def test_uses_current_healthy_snapshot(self):
        snapshot = actions.fbo.choose_wb_stock_snapshot(
            [
                {"date": "2026-07-13", "total_fbo": 200_000, "positive_skus": 300},
                {"date": "2026-07-12", "total_fbo": 210_000, "positive_skus": 310},
            ],
            date(2026, 7, 13),
        )
        self.assertEqual(snapshot["date"], date(2026, 7, 13))
        self.assertFalse(snapshot["fallback_used"])

    def test_falls_back_from_empty_current_snapshot(self):
        snapshot = actions.fbo.choose_wb_stock_snapshot(
            [
                {"date": "2026-07-13", "total_fbo": 0, "positive_skus": 0},
                {"date": "2026-07-12", "total_fbo": 207_335, "positive_skus": 316},
            ],
            date(2026, 7, 13),
        )
        self.assertEqual(snapshot["date"], date(2026, 7, 12))
        self.assertTrue(snapshot["fallback_used"])
        self.assertEqual(snapshot["fallback_reason"], "latest_snapshot_empty")

    def test_falls_back_from_partial_anomalous_snapshot(self):
        snapshot = actions.fbo.choose_wb_stock_snapshot(
            [
                {"date": "2026-07-13", "total_fbo": 10_000, "positive_skus": 20},
                {"date": "2026-07-12", "total_fbo": 207_335, "positive_skus": 316},
            ],
            date(2026, 7, 13),
        )
        self.assertEqual(snapshot["date"], date(2026, 7, 12))
        self.assertEqual(snapshot["fallback_reason"], "latest_snapshot_anomalous_drop")

    def test_rejects_stale_snapshot(self):
        with self.assertRaisesRegex(RuntimeError, "Нет свежего валидного среза"):
            actions.fbo.choose_wb_stock_snapshot(
                [{"date": "2026-07-10", "total_fbo": 200_000, "positive_skus": 300}],
                date(2026, 7, 13),
            )

    def test_rejects_all_empty_snapshots(self):
        with self.assertRaisesRegex(RuntimeError, "Все доступные срезы"):
            actions.fbo.choose_wb_stock_snapshot(
                [{"date": "2026-07-13", "total_fbo": 0, "positive_skus": 0}],
                date(2026, 7, 13),
            )


class PachcaSendGuardTest(unittest.TestCase):
    def test_does_not_upload_or_send_empty_action_report(self):
        empty_report = {
            "items": 0,
            "base_items": 286,
            "stock_snapshot": {"date": "2026-07-13", "total_fbo": 200_000},
        }
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"PACHCA_TOKEN": "token", "PACHCA_CHAT_ID": "123"}),
            mock.patch.object(sender, "build_report", return_value=empty_report),
            mock.patch.object(sender, "upload_file") as upload_file,
            mock.patch.object(sender, "send_message") as send_message,
            contextlib.redirect_stdout(output),
        ):
            sender.main()

        upload_file.assert_not_called()
        send_message.assert_not_called()
        self.assertIn('"status": "skipped"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
