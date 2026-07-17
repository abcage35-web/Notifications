#!/usr/bin/env python3
import unittest
from datetime import date

import build_sheet_supplies_md as fbo


class SupplySheetDateTest(unittest.TestCase):
    def test_uses_fact_date_when_present(self):
        self.assertEqual(
            fbo.supply_sheet_row_date(["18.07.2026", "19.07.2026"]),
            date(2026, 7, 19),
        )

    def test_falls_back_to_plan_date_when_fact_date_missing(self):
        self.assertEqual(
            fbo.supply_sheet_row_date(["18.07.2026", ""]),
            date(2026, 7, 18),
        )

    def test_falls_back_to_plan_date_when_fact_date_invalid(self):
        self.assertEqual(
            fbo.supply_sheet_row_date(["18.07.2026", "not-a-date"]),
            date(2026, 7, 18),
        )


if __name__ == "__main__":
    unittest.main()
