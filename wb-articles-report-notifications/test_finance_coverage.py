import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import build_wb_articles_marketer_report as report


class FinanceCoverageTest(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 11, 1)
        self.source = [
            {"date_at": "2026-11-01T00:00:00.000Z", "account_id": 1, "finance_revenue": "10000.00"},
            {"date_at": "2026-11-01", "account_id": 2, "finance_revenue": "20000.00"},
        ]
        self.db = Mock()
        self.db.query.return_value = self.source

    def validate(self, rows):
        report.validate_finance_coverage(self.db, rows, self.day, self.day)

    def test_complete_finance_accepts_revenue_only_and_spend_only_rows(self):
        rows = [
            {"date_at": "2026-11-01", "account_id": 1, "finance_revenue": "8000.00"},
            {"date_at": "2026-11-01", "account_id": 1, "finance_revenue": "2000.00"},
            self.source[1],
            {"date_at": "2026-11-01", "account_id": 11, "finance_revenue": "0"},
        ]
        self.validate(rows)

    def test_empty_finance_source_blocks_report(self):
        self.db.query.return_value = []
        with self.assertRaisesRegex(RuntimeError, "no data for: 2026-11-01"):
            self.validate([])

    def test_missing_day_blocks_report_even_with_complete_other_days(self):
        with self.assertRaisesRegex(RuntimeError, "no data for: 2026-11-02"):
            report.validate_finance_coverage(self.db, self.source, self.day, date(2026, 11, 2))

    def test_missing_or_duplicated_finance_rows_block_report(self):
        for rows in [self.source[:1], self.source + [self.source[0]]]:
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(RuntimeError, "Incomplete finance"):
                    self.validate(rows)

    def test_account_mismatch_blocks_report_even_when_global_revenue_matches(self):
        rows = [
            {**self.source[0], "finance_revenue": "20000.00"},
            {**self.source[1], "finance_revenue": "10000.00"},
        ]
        with self.assertRaisesRegex(RuntimeError, "Incomplete finance"):
            self.validate(rows)

    def test_confirmed_zero_revenue_is_allowed_but_drr_is_undefined(self):
        source = [{**self.source[0], "finance_revenue": "0"}]
        self.db.query.return_value = source
        self.validate(source)
        self.assertEqual(report.drr_label({"drr": None}), "нет данных")
        self.assertEqual(report.drr_label({"drr": Decimal("0")}), "0.00%")

    def test_revenue_only_sku_contributes_to_message_and_niche(self):
        raw_rows = [
            {**self.source[0], "sku": "101", "cabinet": "Стас 1", "legal_entity_name": "Сытин",
             "category": "Гантели", "ad_spend": "1000"},
            {**self.source[1], "sku": "102", "cabinet": "Паша 1", "legal_entity_name": "Карпачев",
             "category": "Одеяла", "ad_spend": "0"},
        ]
        with patch.object(report, "load_marketer_by_article", return_value={}):
            rows = report.enrich_rows(raw_rows, self.day, {})
        totals = report.metric_totals(rows)
        self.assertEqual(totals["revenue"], Decimal("30000"))
        self.assertEqual(totals["ad_spend"], Decimal("1000"))
        self.assertEqual(len(report.build_niche_summaries(rows, self.day)), 2)
        message = report.build_message(rows, self.day, self.day)
        self.assertIn("`30 000 ₽`", message)
        self.assertIn("**`3.33%`**", message)


if __name__ == "__main__":
    unittest.main()
