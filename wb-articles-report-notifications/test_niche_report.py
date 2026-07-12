#!/usr/bin/env python3
import unittest
from datetime import date
from decimal import Decimal

from build_wb_articles_marketer_report import (
    build_niche_detail_message,
    build_niche_summaries,
    build_niche_summary_message,
)


def row(day, sku, revenue, spend, orders, *, plan_rub, plan_qty, planned_drr, category="Массажеры электрические"):
    return {
        "date": date(2026, 7, day),
        "category": category,
        "sku": str(sku),
        "account_id": 2,
        "marketer": "@fallback",
        "finance_revenue": Decimal(str(revenue)),
        "ad_spend": Decimal(str(spend)),
        "orders_qty": Decimal(str(orders)),
        "plan_rub": Decimal(str(plan_rub)),
        "plan_qty": Decimal(str(plan_qty)),
        "planned_drr": Decimal(str(planned_drr)),
    }


class NicheReportTest(unittest.TestCase):
    def test_mtd_plan_is_prorated_and_not_duplicated_by_daily_rows(self):
        rows = [
            row(1, 101, 4_000_000, 400_000, 40, plan_rub=31_000_000, plan_qty=310, planned_drr=8),
            row(10, 101, 5_000_000, 320_000, 50, plan_rub=31_000_000, plan_qty=310, planned_drr=8),
        ]

        summary = build_niche_summaries(rows, date(2026, 7, 10), {"Массажеры электрические": 6420})[0]

        self.assertEqual(summary["plan_revenue"], Decimal("10000000"))
        self.assertEqual(summary["plan_orders"], Decimal("100"))
        self.assertEqual(summary["revenue_completion"], Decimal("90"))
        self.assertEqual(summary["orders_completion"], Decimal("90"))
        self.assertEqual(summary["actual_drr"], Decimal("8"))
        self.assertEqual(summary["planned_drr"], Decimal("8"))
        self.assertEqual(summary["active_skus"], 1)
        self.assertEqual(summary["season_type"], "all_season")
        self.assertEqual(summary["fbo"], Decimal("6420"))
        self.assertEqual(summary["turnover_days"], Decimal("713.3333333333333333333333333"))
        self.assertEqual(summary["marketer"], "@a.beaver")

    def test_active_sku_threshold_is_strictly_above_5000(self):
        rows = [
            row(10, 101, 5_000, 0, 1, plan_rub=31_000, plan_qty=31, planned_drr=8),
            row(10, 102, 0, 5_001, 0, plan_rub=0, plan_qty=0, planned_drr=0),
        ]

        summary = build_niche_summaries(rows, date(2026, 7, 10))[0]

        self.assertEqual(summary["active_skus"], 1)

    def test_niches_without_active_skus_are_excluded(self):
        rows = [
            row(10, 101, 5_000, 0, 1, plan_rub=31_000, plan_qty=31, planned_drr=8),
        ]

        summaries = build_niche_summaries(rows, date(2026, 7, 10))

        self.assertEqual(summaries, [])

    def test_message_uses_compact_format_and_status_chips(self):
        rows = [
            row(10, 101, 9_000_000, 720_000, 90, plan_rub=31_000_000, plan_qty=310, planned_drr=8),
        ]

        summary_message = build_niche_summary_message(
            rows,
            date(2026, 7, 10),
            {"Массажеры электрические": 6420},
        )
        detail_message = build_niche_detail_message(
            rows,
            date(2026, 7, 10),
            {"Массажеры электрические": 6420},
        )

        self.assertIn("**Сводная по маркетологам**", summary_message)
        self.assertNotIn("**Детализация по нишам**", summary_message)
        self.assertIn("**♾️ ВСЕСЕЗОННЫЕ**", summary_message)
        self.assertIn(
            "@a.beaver\n**♾️ ВСЕСЕЗОННЫЕ**\n"
            "• **Массажеры электрические · 1 SKU**\n"
            "• • `Выручка 🟢 90,0%` · `ДРР 🟢 8,0% / 8,0%` · `💸 Доля трат 100,0%` · "
            "`🔄 Оборачиваемость 713,3 дн.`",
            summary_message,
        )
        self.assertIn("**Детализация по нишам**", detail_message)
        self.assertNotIn("**Сводная по маркетологам**", detail_message)
        self.assertIn("**Массажеры электрические · ♾️ Всесезонная · 1 SKU** · @a.beaver", detail_message)
        self.assertIn("`Выручка 🟢` · `ДРР 🟢` · `💸 Доля трат 100,0%`", detail_message)
        self.assertIn("💰 Выручка `90,0%` — `9,0 / 10,0 млн ₽`", detail_message)
        self.assertIn("🎯 ДРР `8,0% / 8,0%` — траты `720,0 тыс. ₽`", detail_message)
        self.assertIn("🛒 Заказы `90,0%` — `90 / 100`", detail_message)
        self.assertIn("📦 FBO `6 420 шт.` — `713,3 дн.`", detail_message)

    def test_status_matches_the_displayed_one_decimal_values(self):
        rows = [
            row(10, 101, 9_000_000, 651_600, 90, plan_rub=31_000_000, plan_qty=310, planned_drr=7.2),
        ]

        message = build_niche_detail_message(rows, date(2026, 7, 10))

        self.assertIn("`ДРР 🟢`", message)
        self.assertIn("🎯 ДРР `7,2% / 7,2%`", message)


if __name__ == "__main__":
    unittest.main()
