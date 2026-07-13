#!/usr/bin/env python3
import unittest
from decimal import Decimal

from niche_action_analytics import product_decision


def product(**overrides):
    row = {
        "drr": Decimal("8"),
        "drr_plan": Decimal("9"),
        "mechanics": [
            {
                "mechanic": "Единая ставка",
                "spend": Decimal("1000"),
                "drr": Decimal("7"),
            }
        ],
        "turnover_days": Decimal("30"),
        "future_stock_days": Decimal("40"),
        "incoming_qty": Decimal("0"),
        "fbo_stock": Decimal("100"),
        "revenue_plan": Decimal("100000"),
        "plan_pct": Decimal("100"),
        "rating": Decimal("4.8"),
        "reviews": 1000,
        "yesterday_spend": Decimal("1000"),
        "seasonal": False,
        "fbo_supply_checked": True,
        "fbo_supply_confirmed": False,
        "recent_price_increase": False,
        "last_price_increase_date": "",
        "margin_pre_pct": Decimal("20"),
        "margin_post_pct": Decimal("12"),
        "margin_available": True,
    }
    row.update(overrides)
    return row


class NicheActionAnalyticsTest(unittest.TestCase):
    def test_low_fbo_with_spend_below_300_is_already_inactive(self):
        decision = product_decision(
            product(turnover_days=Decimal("2.5"), yesterday_spend=Decimal("299"))
        )

        self.assertEqual(decision["methods"], ["FBO"])
        self.assertIn("фактически неактивна", decision["action"])
        self.assertNotIn("Выключить", decision["action"])

    def test_recent_price_increase_blocks_simultaneous_ad_cut(self):
        decision = product_decision(
            product(
                drr=Decimal("14"),
                drr_plan=Decimal("9"),
                recent_price_increase=True,
                last_price_increase_date="2026-07-13",
            )
        )

        self.assertIn("Не сокращать РК 2–3 дня", decision["action"])
        self.assertEqual(decision["methods"], ["Цена", "Реклама", "Наблюдение"])

    def test_strong_overperformance_scales_best_mechanic(self):
        decision = product_decision(
            product(plan_pct=Decimal("150"), turnover_days=Decimal("35"))
        )

        self.assertIn("Масштабировать", decision["action"])
        self.assertEqual(decision["methods"], ["Реклама"])

    def test_negative_margin_blocks_price_reduction(self):
        decision = product_decision(
            product(margin_pre_pct=Decimal("5"), margin_post_pct=Decimal("-3"))
        )

        self.assertIn("снижение цены", decision["action"])
        self.assertEqual(decision["methods"], ["Экономика", "Цена"])


if __name__ == "__main__":
    unittest.main()
