#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
FBO_ROOT = ROOT.parent / "wb-fbo-supply-notifications"
sys.path.insert(0, str(FBO_ROOT))

from build_sheet_supplies_md import load_marketer_by_article  # noqa: E402
from custom_wb_fbo_supplies import McpSql  # noqa: E402


REPORT_TZ = ZoneInfo(os.getenv("REPORT_TZ", "Europe/Moscow"))
REPORT_RUN_LABEL = os.getenv("REPORT_RUN_LABEL", "09:00 по МСК")
DEFAULT_WINDOW_DAYS = int(os.getenv("REPORT_WINDOW_DAYS", "30"))
OLD_IP_REPORT_PATH = os.getenv("OLD_IP_REPORT_PATH", "")
REVENUE_KEY = "finance_revenue"
ACTIVE_NICHE_SKU_THRESHOLD = Decimal("5000")
CATEGORY_MARKETER_NAMES = {
    "Сумки": "Саша М.",
    "Машинки": "Саша Н.",
    "Конструкторы": "Саша Н.",
    "Наборы для рисования": "Саша Н.",
    "Настольные игры для детей": "Саша Н.",
    "Железные дороги": "Саша Н.",
    "Роботы": "Саша Н.",
    "Радиоуправляемые игрушки": "Саша Н.",
    "Игрушечное оружие": "Саша М.",
    "Куклы": "Саша М.",
    "Игрушечная посуда": "Саша М.",
    "Рюкзаки": "Саша М.",
    "Колготки": "Антон",
    "Эспандеры": "Саша Н.",
    "Игровые наборы": "Саша М.",
    "Фигурки-игрушки": "Саша М.",
    "Пеналы": "Саша М.",
    "Одеяла": "Саша Н.",
    "Наборы для лепки": "Саша Н.",
    "Коврики спортивные": "Саша М.",
    "Упоры для отжиманий": "Саша Н.",
    "Утяжелители": "Саша М.",
    "Круги для плавания": "Саша М.",
    "Матрасы для плавания": "Саша М.",
    "Тренажеры": "Саша М.",
    "Палатки": "Саша Н.",
    "Адаптеры": "Антон",
    "Столы туристические": "Саша Н.",
    "Массажеры электрические": "Антон",
    "Обручи": "Саша М.",
    "Чайники электрические": "Антон",
    "Игровые коврики": "Саша Н.",
    "Календари": "Саша Н.",
    "Наборы для поделок": "Саша Н.",
    "Кастрюли": "Саша М.",
    "Гантели": "Саша М.",
    "Кашпо": "Саша Н.",
    "Массажеры механические": "Антон",
    "Кукольные домики": "Саша М.",
    "Игровые палатки": "Саша М.",
    "Самолеты и вертолеты": "Саша Н.",
    "Головоломки": "Саша Н.",
    "Снуды": "Саша М.",
    "Горшки для цветов": "Саша Н.",
    "Опрыскиватели": "Саша Н.",
    "Спортивные игровые наборы": "Саша М.",
    "Этажерки": "Саша Н.",
    "Блоки для йоги": "Саша Н.",
    "Ирригаторы": "Антон",
    "Швабры": "Антон",
    "Стулья": "Саша Н.",
    "Коврики детские": "Саша Н.",
    "Сушилки для белья": "Саша М.",
    "Фитболы": "Саша Н.",
    "Грифы": "Саша М.",
    "Диски для штанг и гантелей": "Саша М.",
    "Табуреты детские": "Саша Н.",
    "Светильники уличные": "Саша Н.",
    "Автотреки": "Саша Н.",
    "Шнуровки": "Саша М.",
    "Видеокарты": "Антон",
    "Модули памяти": "Антон",
    "Тенты для бассейнов": "Антон",
    "Ролики массажные": "Саша М.",
    "Походный душ": "Антон",
    "Велотренажеры": "Саша М.",
    "Аксессуары для массажеров": "Антон",
    "Беговые дорожки": "Саша М.",
    "Тренажеры эллиптические": "Саша М.",
    "Зажимы на гриф": "Саша М.",
    "Кресла компьютерные": "Саша Н.",
    "Комплекты садовой мебели": "Антон",
    "Игрушечные парковки": "Саша Н.",
    "Сюжетные игровые наборы": "Саша Н.",
    "Лестницы для бассейнов": "Антон",
    "Шатры и беседки": "Антон",
    "Аксессуары для бассейна": "Антон",
    "Кресла игровые": "Саша Н.",
    "Бассейны надувные": "Саша Н.",
    "Бассейны каркасные": "Саша М.",
    "Валики спортивные": "Саша Н.",
    "Бассейн надувной": "Саша Н.",
    "Бассейн каркасный": "Саша М.",
    "Спортивный товар": "Антон",
    "3D-ручки": "Саша М.",
    "Вешалки-плечики": "Саша М.",
}
CATEGORY_MARKETER_MENTIONS = {
    "Саша М.": "@a.manokhin",
    "Саша Н.": "@a.nekrasov",
    "Антон": "@a.beaver",
}
NICHE_SEASON_TYPES = {
    "Аксессуары для бассейна": "seasonal",
    "Бассейны каркасные": "seasonal",
    "Бассейны надувные": "seasonal",
    "Блоки для йоги": "all_season",
    "Гантели": "all_season",
    "Игровые наборы": "all_season",
    "Игровые палатки": "all_season",
    "Игрушечное оружие": "all_season",
    "Коврики детские": "all_season",
    "Коврики спортивные": "all_season",
    "Колготки": "seasonal",
    "Колготки для малышей": "seasonal",
    "Комплекты садовой мебели": "seasonal",
    "Конструкторы": "all_season",
    "Круги для плавания": "seasonal",
    "Лестницы для бассейнов": "seasonal",
    "Массажеры электрические": "all_season",
    "Матрасы для плавания": "seasonal",
    "Одеяла": "seasonal",
    "Опрыскиватели": "seasonal",
    "Походный душ": "seasonal",
    "Пылесосы": "all_season",
    "Радиоуправляемые игрушки": "all_season",
    "Ролики массажные": "all_season",
    "Светильники уличные": "seasonal",
    "Скиммеры": "seasonal",
    "Столы туристические": "seasonal",
    "Стулья": "seasonal",
    "Тенты для бассейнов": "seasonal",
    "Тренажеры": "all_season",
    "Фитболы": "all_season",
    "Шатры и беседки": "seasonal",
    "Швабры": "all_season",
    "Этажерки": "all_season",
}
SEASON_META = {
    "seasonal": {"summary": "☀️ Сезонные", "detail": "☀️ Сезонная", "order": 0},
    "all_season": {"summary": "♾️ Всесезонные", "detail": "♾️ Всесезонная", "order": 1},
    "unknown": {"summary": "❔ Сезонность не определена", "detail": "❔ Не определена", "order": 2},
}
MESSAGE_NAME_REPLACEMENTS = {
    "ИП Карпачев": "Паша 1",
    "ИП Сытин": "Стас 1",
}
IP_MESSAGE_NAME_REPLACEMENTS = {
    "ИП Карпачев": "Паша 1 + Паша 2",
    "ИП Сытин": "Стас 1 + Стас 2",
}
IP_MESSAGE_ORDER = {
    "ИП Сытин": 0,
    "ИП Карпачев": 1,
}
CABINET_MESSAGE_ORDER = {
    "ИП Сытин": 0,
    "Стас 2": 1,
    "ИП Карпачев": 2,
    "Паша 2": 3,
}

HEADERS = [
    "date",
    "month",
    "marketplace",
    "cabinet",
    "ip",
    "marketer",
    "category",
    "sku",
    "product_name",
    "current_stock",
    "open_card_count",
    "impressions",
    "clicks",
    "ctr",
    "baskets",
    "cr1",
    "orders_qty",
    "orders_rub",
    "cr2",
    "buyouts_qty",
    "cr3",
    "ad_baskets",
    "ad_orders_qty",
    "ad_orders_rub",
    "ad_cr1",
    "ad_cr2",
    "ad_spend",
    "drr",
    "ad_drr",
    "cpc",
    "cpo",
    "avg_price",
    "plan_qty",
    "plan_rub",
    "plan_qty_daily",
    "plan_rub_daily",
    "plan_price",
    "planned_drr",
    "finance_revenue",
    "margin_rub",
    "margin_percent",
    "orders_prev_day",
    "orders_delta",
    "orders_delta_pct",
    "revenue_prev_day",
    "revenue_delta",
    "revenue_delta_pct",
    "category_spend_share",
    "ctr_vs_category_best",
    "cr1_vs_category_best",
    "cr2_vs_category_best",
    "orders_qty_mtd",
    "orders_rub_mtd",
    "plan_qty_completion_pct",
    "plan_rub_completion_pct",
    "forecast_qty_month",
    "forecast_rub_month",
    "forecast_qty_plan_pct",
    "forecast_rub_plan_pct",
    "oos_days_left",
    "oos_risk",
]


def today() -> date:
    return datetime.now(REPORT_TZ).date()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def month_start(value: date) -> date:
    return value.replace(day=1)


def dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def pct(numerator, denominator):
    numerator = dec(numerator)
    denominator = dec(denominator)
    if denominator == 0:
        return None
    return numerator / denominator * Decimal("100")


def safe_div(numerator, denominator):
    numerator = dec(numerator)
    denominator = dec(denominator)
    if denominator == 0:
        return None
    return numerator / denominator


def normalize_ip(value):
    text = (value or "").strip()
    if not text:
        return "-"
    return re.sub(r"^Ип\b", "ИП", text)


def md_cell(value):
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def fmt_int(value):
    value = dec(value)
    return f"{int(value):,}".replace(",", " ")


def fmt_decimal(value, digits=2, blank_if_none=True, zero_plain=True):
    if value is None:
        return "" if blank_if_none else "0"
    value = dec(value)
    if zero_plain and value == 0:
        return "0"
    q = Decimal("1") if digits == 0 else Decimal("1." + "0" * digits)
    return f"{value.quantize(q):,}".replace(",", " ")


def fmt_rub(value):
    return f"{fmt_decimal(value, digits=0, zero_plain=False)} ₽"


def fmt_date(value: date):
    return value.strftime("%d.%m.%Y")


def fmt_one(value):
    if value is None:
        return ""
    value = dec(value)
    return f"{value.quantize(Decimal('1.0')):,}".replace(",", " ")


def fmt_percent(value, blank_if_none=True):
    if value is None:
        return "" if blank_if_none else "0.00%"
    return f"{dec(value).quantize(Decimal('1.00'))}%"


def fmt_percent_one(value, blank="-"):
    if value is None:
        return blank
    return f"{dec(value).quantize(Decimal('1.0'))}%".replace(".", ",")


def rounded_one(value):
    if value is None:
        return None
    return dec(value).quantize(Decimal("1.0"))


def fmt_days(value):
    if value is None:
        return "-"
    return f"{str(rounded_one(value)).replace('.', ',')} дн."


def compact_scale(values):
    largest = max((abs(dec(value)) for value in values), default=Decimal("0"))
    if largest >= Decimal("1000000"):
        return Decimal("1000000"), "млн"
    if largest >= Decimal("1000"):
        return Decimal("1000"), "тыс."
    return Decimal("1"), ""


def fmt_compact_value(value, currency=False):
    scale, unit = compact_scale([value])
    if scale == 1:
        label = fmt_int(value)
    else:
        label = str((dec(value) / scale).quantize(Decimal("1.0"))).replace(".", ",")
    suffix = " ".join(part for part in (unit, "₽" if currency else "") if part)
    return f"{label} {suffix}".strip()


def fmt_compact_pair(actual, plan, currency=False):
    scale, unit = compact_scale([actual, plan])
    if scale == 1:
        actual_label = fmt_int(actual)
        plan_label = fmt_int(plan)
    else:
        actual_label = str((dec(actual) / scale).quantize(Decimal("1.0"))).replace(".", ",")
        plan_label = str((dec(plan) / scale).quantize(Decimal("1.0"))).replace(".", ",")
    suffix = " ".join(part for part in (unit, "₽" if currency else "") if part)
    return f"{actual_label} / {plan_label}{(' ' + suffix) if suffix else ''}"


def fmt_plan_qty_daily(value):
    if value is None:
        return ""
    value = dec(value)
    if value == 0:
        return "0"
    return fmt_one(value)


def load_old_ip_by_sku(path_text: str) -> dict[str, str]:
    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    if not path.exists():
        return {}

    headers = None
    mapping = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| date |"):
            headers = [cell.strip() for cell in line.strip("|").split("|")]
            continue
        if not headers or not line.startswith("| 20"):
            continue
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        sku = row.get("sku")
        ip = row.get("ip")
        if sku and ip:
            mapping.setdefault(str(sku), ip)
    return mapping


def query_rows(db: McpSql, query_from: date, date_to: date, stock_date: date):
    plan_from = month_start(query_from)
    plan_to = month_start(date_to)
    sql = f"""
    WITH current_stock AS (
        SELECT CAST(stock.sku AS UNSIGNED) AS sku_num,
               stock.account_id,
               SUM(COALESCE(stock.fbo_real, 0)) AS current_stock
        FROM mp.mp_core__realtime_stocks_data stock
        WHERE stock.date = '{stock_date.isoformat()}'
          AND stock.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
          AND stock.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, stock.account_id
    ),
    daily_keys AS (
        SELECT DISTINCT s.date_at, s.account_id, CAST(s.sku AS UNSIGNED) AS sku_num
        FROM mp.wb_core__campaign_stat_daily_sku s
        WHERE s.date_at BETWEEN '{query_from.isoformat()}' AND '{date_to.isoformat()}'
          AND COALESCE(s.consumptions, 0) <> 0

        UNION

        SELECT DISTINCT fin.date AS date_at, fin.account_id, CAST(card.sku AS UNSIGNED) AS sku_num
        FROM mp.mp_core__realtime_finance fin
        JOIN mp.wb_core__card card
          ON card.card_id = fin.card_id
         AND card.account_id = fin.account_id
        WHERE fin.date BETWEEN '{query_from.isoformat()}' AND '{date_to.isoformat()}'
          AND fin.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
          AND COALESCE(fin.revenue, 0) <> 0
    ),
    key_skus AS (
        SELECT DISTINCT account_id, sku_num
        FROM daily_keys
    ),
    funnel AS (
        SELECT f.date_at, f.account_id, CAST(f.sku AS UNSIGNED) AS sku_num,
               SUM(COALESCE(f.open_card_count, 0)) AS open_card_count,
               SUM(COALESCE(f.add_to_cart_count, 0)) AS baskets,
               SUM(COALESCE(f.orders_count, 0)) AS orders_qty,
               SUM(COALESCE(f.orders_sum, 0)) AS orders_rub,
               SUM(COALESCE(f.buyouts_count, 0)) AS buyouts_qty
        FROM mp.wb_core__funnel f
        JOIN daily_keys k
          ON k.date_at = f.date_at
         AND k.account_id = f.account_id
         AND k.sku_num = CAST(f.sku AS UNSIGNED)
        GROUP BY f.date_at, f.account_id, sku_num
    ),
    ads AS (
        SELECT s.date_at, s.account_id, CAST(s.sku AS UNSIGNED) AS sku_num,
               SUM(COALESCE(s.impressions, 0)) AS impressions,
               SUM(COALESCE(s.clicks, 0)) AS clicks,
               SUM(COALESCE(s.cart_count, 0)) AS ad_baskets,
               SUM(COALESCE(s.orders_count, 0)) AS ad_orders_qty,
               SUM(COALESCE(s.orders_money, 0)) AS ad_orders_rub,
               SUM(COALESCE(s.consumptions, 0)) AS ad_spend
        FROM mp.wb_core__campaign_stat_daily_sku s
        JOIN daily_keys k
          ON k.date_at = s.date_at
         AND k.account_id = s.account_id
         AND k.sku_num = CAST(s.sku AS UNSIGNED)
        GROUP BY s.date_at, s.account_id, sku_num
    ),
    card_info AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               card.account_id,
               MAX(COALESCE(card.short_name, card.name)) AS product_name,
               MAX(card.object) AS category,
               MAX(card.card_id) AS card_id
        FROM mp.wb_core__card card
        JOIN key_skus k
          ON k.sku_num = CAST(card.sku AS UNSIGNED)
         AND k.account_id = card.account_id
        GROUP BY sku_num, card.account_id
    ),
    plans AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               card.account_id,
               plan.planning_date,
               SUM(COALESCE(plan.correct_count, plan.planned_count, 0)) AS plan_qty,
               SUM(
                   COALESCE(plan.correct_count, plan.planned_count, 0)
                   * COALESCE(plan.correct_price, plan.planned_price, 0)
               ) AS plan_rub,
               MAX(COALESCE(plan.correct_price, plan.planned_price, 0)) AS plan_price,
               MAX(COALESCE(plan.planned_drr, 0)) AS planned_drr,
               MAX(COALESCE(plan.correct_margin, plan.planed_margin, 0)) AS planned_margin
        FROM key_skus k
        JOIN mp.wb_core__card card
          ON k.sku_num = CAST(card.sku AS UNSIGNED)
         AND k.account_id = card.account_id
        LEFT JOIN mp.mp_core__sales_plan plan
          ON plan.card_id = card.card_id
         AND plan.account_id = card.account_id
         AND plan.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
         AND plan.planning_date BETWEEN '{plan_from.isoformat()}' AND '{plan_to.isoformat()}'
        GROUP BY sku_num, card.account_id, plan.planning_date
    ),
    finance AS (
        SELECT fin.date,
               fin.account_id,
               CAST(card.sku AS UNSIGNED) AS sku_num,
               SUM(COALESCE(fin.revenue, 0)) AS finance_revenue,
               SUM(COALESCE(fin.margin, 0)) AS finance_margin
        FROM mp.mp_core__realtime_finance fin
        JOIN mp.wb_core__card card
          ON card.card_id = fin.card_id
         AND card.account_id = fin.account_id
        JOIN key_skus k
          ON k.sku_num = CAST(card.sku AS UNSIGNED)
         AND k.account_id = card.account_id
        WHERE fin.date BETWEEN '{query_from.isoformat()}' AND '{date_to.isoformat()}'
          AND fin.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
        GROUP BY fin.date, fin.account_id, sku_num
    ),
    card_all AS (
        SELECT CAST(sku AS UNSIGNED) AS sku_num,
               MAX(legal_entity_name) AS legal_entity_name,
               MAX(crm_name) AS crm_name,
               MAX(subject_name) AS subject_name
        FROM mp.vw_mp_core__card_all
        JOIN (SELECT DISTINCT sku_num FROM key_skus) sku_filter
          ON sku_filter.sku_num = CAST(sku AS UNSIGNED)
        WHERE mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
        GROUP BY sku_num
    )
    SELECT k.date_at,
           k.account_id,
           account.account_name_alias AS cabinet,
           account.name AS account_name,
           CAST(k.sku_num AS CHAR) AS sku,
           COALESCE(cs.current_stock, 0) AS current_stock,
           COALESCE(ci.product_name, ca.crm_name, '-') AS product_name,
           COALESCE(ci.category, ca.subject_name, '-') AS category,
           ca.legal_entity_name,
           COALESCE(f.open_card_count, 0) AS open_card_count,
           COALESCE(a.impressions, 0) AS impressions,
           COALESCE(a.clicks, 0) AS clicks,
           COALESCE(f.baskets, 0) AS baskets,
           COALESCE(f.orders_qty, 0) AS orders_qty,
           COALESCE(f.orders_rub, 0) AS orders_rub,
           COALESCE(f.buyouts_qty, 0) AS buyouts_qty,
           COALESCE(a.ad_baskets, 0) AS ad_baskets,
           COALESCE(a.ad_orders_qty, 0) AS ad_orders_qty,
           COALESCE(a.ad_orders_rub, 0) AS ad_orders_rub,
           COALESCE(a.ad_spend, 0) AS ad_spend,
           COALESCE(p.plan_qty, 0) AS plan_qty,
           COALESCE(p.plan_rub, 0) AS plan_rub,
           COALESCE(p.plan_price, 0) AS plan_price,
           COALESCE(p.planned_drr, 0) AS planned_drr,
           COALESCE(p.planned_margin, 0) AS planned_margin,
           COALESCE(fin.finance_revenue, 0) AS finance_revenue,
           COALESCE(fin.finance_margin, 0) AS finance_margin
    FROM daily_keys k
    LEFT JOIN current_stock cs
      ON cs.sku_num = k.sku_num
     AND cs.account_id = k.account_id
    LEFT JOIN funnel f
      ON f.date_at = k.date_at
     AND f.account_id = k.account_id
     AND f.sku_num = k.sku_num
    LEFT JOIN ads a
      ON a.date_at = k.date_at
     AND a.account_id = k.account_id
     AND a.sku_num = k.sku_num
    LEFT JOIN card_info ci
      ON ci.sku_num = k.sku_num
     AND ci.account_id = k.account_id
    LEFT JOIN plans p
      ON p.sku_num = k.sku_num
     AND p.account_id = k.account_id
     AND p.planning_date = DATE_SUB(k.date_at, INTERVAL (DAYOFMONTH(k.date_at) - 1) DAY)
    LEFT JOIN finance fin
      ON fin.date = k.date_at
     AND fin.account_id = k.account_id
     AND fin.sku_num = k.sku_num
    LEFT JOIN card_all ca
      ON ca.sku_num = k.sku_num
    LEFT JOIN mp.accounts account
      ON account.id = k.account_id
    WHERE COALESCE(fin.finance_revenue, 0) <> 0
       OR COALESCE(a.ad_spend, 0) <> 0
    ORDER BY k.date_at, cabinet, category, k.sku_num;
    """
    return db.query(sql)


def resolve_stock_date(db: McpSql, requested_stock_date: date) -> date:
    sql = f"""
    SELECT MAX(stock.date) AS stock_date
    FROM mp.mp_core__realtime_stocks_data stock
    WHERE stock.date <= '{requested_stock_date.isoformat()}'
      AND stock.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
    """
    rows = db.query(sql)
    if not rows or not rows[0].get("stock_date"):
        return requested_stock_date
    return parse_date(str(rows[0]["stock_date"])[:10])


def query_niche_stocks(db: McpSql, stock_date: date):
    sql = f"""
    WITH stock_by_sku AS (
        SELECT CAST(stock.sku AS UNSIGNED) AS sku_num,
               stock.account_id,
               SUM(COALESCE(stock.fbo_real, 0)) AS current_stock
        FROM mp.mp_core__realtime_stocks_data stock
        WHERE stock.date = '{stock_date.isoformat()}'
          AND stock.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
          AND stock.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, stock.account_id
    ),
    card_category AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               card.account_id,
               MAX(COALESCE(card.object, card_all.subject_name, 'Без ниши')) AS category
        FROM mp.wb_core__card card
        LEFT JOIN mp.vw_mp_core__card_all card_all
          ON CAST(card_all.sku AS UNSIGNED) = CAST(card.sku AS UNSIGNED)
         AND card_all.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
        GROUP BY sku_num, card.account_id
    )
    SELECT COALESCE(category.category, 'Без ниши') AS category,
           SUM(stock.current_stock) AS current_stock
    FROM stock_by_sku stock
    LEFT JOIN card_category category
      ON category.sku_num = stock.sku_num
     AND category.account_id = stock.account_id
    GROUP BY category;
    """
    return {
        str(row.get("category") or "Без ниши"): dec(row.get("current_stock"))
        for row in db.query(sql)
    }


def enrich_rows(raw_rows, calculation_from: date, old_ip_by_sku: dict[str, str]):
    marketers = load_marketer_by_article()
    rows = []
    by_key_date = {}
    for raw in raw_rows:
        row_date = parse_date(str(raw["date_at"])[:10])
        sku = str(raw["sku"])
        account_id = int(raw["account_id"])
        cabinet = raw.get("cabinet") or raw.get("account_name") or "-"
        fallback_ip = raw.get("legal_entity_name") or raw.get("account_name") or cabinet
        ip = old_ip_by_sku.get(sku) or normalize_ip(fallback_ip)
        days_in_month = monthrange(row_date.year, row_date.month)[1]
        plan_qty = dec(raw.get("plan_qty"))
        plan_rub = dec(raw.get("plan_rub"))
        plan_price = dec(raw.get("plan_price"))
        if plan_qty > 0 and plan_rub > 0:
            plan_price = plan_rub / plan_qty
        planned_drr_raw = dec(raw.get("planned_drr"))
        planned_drr_pct = planned_drr_raw * 100 if planned_drr_raw and planned_drr_raw <= 1 else planned_drr_raw
        ad_spend = dec(raw.get("ad_spend"))
        finance_margin = dec(raw.get("finance_margin"))
        finance_revenue = dec(raw.get("finance_revenue"))
        margin_rub = finance_margin - ad_spend if finance_margin or ad_spend else Decimal("0")
        item = {
            "date": row_date,
            "month": row_date.strftime("%Y-%m"),
            "marketplace": "WB",
            "account_id": account_id,
            "cabinet": cabinet,
            "ip": ip,
            "marketer": marketers.get(sku, "-"),
            "category": raw.get("category") or "-",
            "sku": sku,
            "product_name": raw.get("product_name") or "-",
            "current_stock": dec(raw.get("current_stock")),
            "open_card_count": dec(raw.get("open_card_count")),
            "impressions": dec(raw.get("impressions")),
            "clicks": dec(raw.get("clicks")),
            "baskets": dec(raw.get("baskets")),
            "orders_qty": dec(raw.get("orders_qty")),
            "orders_rub": dec(raw.get("orders_rub")),
            "buyouts_qty": dec(raw.get("buyouts_qty")),
            "ad_baskets": dec(raw.get("ad_baskets")),
            "ad_orders_qty": dec(raw.get("ad_orders_qty")),
            "ad_orders_rub": dec(raw.get("ad_orders_rub")),
            "ad_spend": ad_spend,
            "plan_qty": plan_qty,
            "plan_rub": plan_rub,
            "plan_qty_daily": plan_qty / Decimal(days_in_month) if plan_qty else Decimal("0"),
            "plan_rub_daily": plan_rub / Decimal(days_in_month) if plan_rub else Decimal("0"),
            "plan_price": plan_price,
            "planned_drr": planned_drr_pct,
            "margin_rub": margin_rub,
            "margin_percent": pct(margin_rub, finance_revenue),
            "finance_revenue": finance_revenue,
        }
        item["ctr"] = pct(item["clicks"], item["impressions"])
        item["cr1"] = pct(item["baskets"], item["open_card_count"])
        item["cr2"] = pct(item["orders_qty"], item["baskets"])
        item["cr3"] = pct(item["buyouts_qty"], item["orders_qty"])
        item["ad_cr1"] = pct(item["ad_baskets"], item["clicks"])
        item["ad_cr2"] = pct(item["ad_orders_qty"], item["ad_baskets"])
        item["drr"] = pct(item["ad_spend"], item[REVENUE_KEY])
        item["ad_drr"] = pct(item["ad_spend"], item["ad_orders_rub"])
        item["cpc"] = safe_div(item["ad_spend"], item["clicks"])
        item["cpo"] = safe_div(item["ad_spend"], item["orders_qty"])
        item["avg_price"] = safe_div(item["orders_rub"], item["orders_qty"])
        rows.append(item)
        by_key_date[(account_id, sku, row_date)] = item

    for item in rows:
        prev_date = item["date"] - timedelta(days=1)
        prev = by_key_date.get((item["account_id"], item["sku"], prev_date))
        if not prev or item["date"] <= calculation_from:
            item["orders_prev_day"] = None
            item["orders_delta"] = None
            item["orders_delta_pct"] = None
            item["revenue_prev_day"] = None
            item["revenue_delta"] = None
            item["revenue_delta_pct"] = None
            continue
        prev_orders = prev["orders_qty"]
        prev_revenue = prev[REVENUE_KEY]
        item["orders_prev_day"] = prev_orders
        item["orders_delta"] = item["orders_qty"] - prev_orders
        item["orders_delta_pct"] = pct(item["orders_delta"], prev_orders)
        item["revenue_prev_day"] = prev_revenue
        item["revenue_delta"] = item[REVENUE_KEY] - prev_revenue
        item["revenue_delta_pct"] = pct(item["revenue_delta"], prev_revenue)

    cumulative = defaultdict(lambda: {"qty": Decimal("0"), "rub": Decimal("0")})
    for item in sorted(rows, key=lambda row: (row["account_id"], row["sku"], row["month"], row["date"])):
        key = (item["account_id"], item["sku"], item["month"])
        cumulative[key]["qty"] += item["orders_qty"]
        cumulative[key]["rub"] += item["orders_rub"]
        days_elapsed = Decimal(item["date"].day)
        days_in_month = Decimal(monthrange(item["date"].year, item["date"].month)[1])
        forecast_qty = cumulative[key]["qty"] / days_elapsed * days_in_month if days_elapsed else Decimal("0")
        forecast_rub = cumulative[key]["rub"] / days_elapsed * days_in_month if days_elapsed else Decimal("0")
        item["orders_qty_mtd"] = cumulative[key]["qty"]
        item["orders_rub_mtd"] = cumulative[key]["rub"]
        item["plan_qty_completion_pct"] = pct(cumulative[key]["qty"], item["plan_qty"])
        item["plan_rub_completion_pct"] = pct(cumulative[key]["rub"], item["plan_rub"])
        item["forecast_qty_month"] = forecast_qty
        item["forecast_rub_month"] = forecast_rub
        item["forecast_qty_plan_pct"] = pct(forecast_qty, item["plan_qty"])
        item["forecast_rub_plan_pct"] = pct(forecast_rub, item["plan_rub"])
        avg_daily_qty = cumulative[key]["qty"] / days_elapsed if days_elapsed else Decimal("0")
        item["oos_days_left"] = safe_div(item["current_stock"], avg_daily_qty)
        days_left = item["oos_days_left"]
        if days_left is None:
            item["oos_risk"] = ""
        elif days_left <= 7:
            item["oos_risk"] = "high"
        elif days_left <= 14:
            item["oos_risk"] = "medium"
        else:
            item["oos_risk"] = "low"

    category_groups = defaultdict(list)
    for item in rows:
        category_groups[(item["date"], item["cabinet"], item["category"])].append(item)
    for group_items in category_groups.values():
        total_spend = sum((item["ad_spend"] for item in group_items), Decimal("0"))
        best_ctr = max((item["ctr"] or Decimal("0") for item in group_items), default=Decimal("0"))
        best_cr1 = max((item["cr1"] or Decimal("0") for item in group_items), default=Decimal("0"))
        best_cr2 = max((item["cr2"] or Decimal("0") for item in group_items), default=Decimal("0"))
        for item in group_items:
            item["category_spend_share"] = pct(item["ad_spend"], total_spend)
            item["ctr_vs_category_best"] = pct(item["ctr"] or Decimal("0"), best_ctr)
            item["cr1_vs_category_best"] = pct(item["cr1"] or Decimal("0"), best_cr1)
            item["cr2_vs_category_best"] = pct(item["cr2"] or Decimal("0"), best_cr2)

    return sorted(rows, key=lambda row: (row["date"], row["cabinet"], row["category"], int(row["sku"])))


def row_to_markdown(item):
    values = {
        "date": item["date"].isoformat(),
        "month": item["month"],
        "marketplace": "WB",
        "cabinet": md_cell(item["cabinet"]),
        "ip": md_cell(item["ip"]),
        "marketer": md_cell(item["marketer"]),
        "category": md_cell(item["category"]),
        "sku": item["sku"],
        "product_name": md_cell(item["product_name"]),
        "current_stock": fmt_int(item["current_stock"]),
        "open_card_count": fmt_int(item["open_card_count"]),
        "impressions": fmt_int(item["impressions"]),
        "clicks": fmt_int(item["clicks"]),
        "ctr": fmt_percent(item["ctr"]),
        "baskets": fmt_int(item["baskets"]),
        "cr1": fmt_percent(item["cr1"], blank_if_none=False) if item["open_card_count"] else "",
        "orders_qty": fmt_int(item["orders_qty"]),
        "orders_rub": fmt_decimal(item["orders_rub"]),
        "cr2": fmt_percent(item["cr2"]),
        "buyouts_qty": fmt_int(item["buyouts_qty"]),
        "cr3": fmt_percent(item["cr3"]),
        "ad_baskets": fmt_int(item["ad_baskets"]),
        "ad_orders_qty": fmt_int(item["ad_orders_qty"]),
        "ad_orders_rub": fmt_decimal(item["ad_orders_rub"]),
        "ad_cr1": fmt_percent(item["ad_cr1"]),
        "ad_cr2": fmt_percent(item["ad_cr2"]),
        "ad_spend": fmt_decimal(item["ad_spend"]),
        "drr": fmt_percent(item["drr"]),
        "ad_drr": fmt_percent(item["ad_drr"]),
        "cpc": fmt_decimal(item["cpc"]),
        "cpo": fmt_decimal(item["cpo"]),
        "avg_price": fmt_decimal(item["avg_price"]),
        "plan_qty": fmt_int(item["plan_qty"]),
        "plan_rub": fmt_decimal(item["plan_rub"]),
        "plan_qty_daily": fmt_plan_qty_daily(item["plan_qty_daily"]),
        "plan_rub_daily": fmt_decimal(item["plan_rub_daily"]),
        "plan_price": fmt_decimal(item["plan_price"]),
        "planned_drr": fmt_percent(item["planned_drr"], blank_if_none=False),
        "finance_revenue": fmt_decimal(item["finance_revenue"]),
        "margin_rub": fmt_decimal(item["margin_rub"]),
        "margin_percent": fmt_percent(item["margin_percent"], blank_if_none=False) if item["finance_revenue"] else "0.00%",
        "orders_prev_day": "" if item["orders_prev_day"] is None else fmt_int(item["orders_prev_day"]),
        "orders_delta": "" if item["orders_delta"] is None else fmt_int(item["orders_delta"]),
        "orders_delta_pct": fmt_percent(item["orders_delta_pct"]),
        "revenue_prev_day": "" if item["revenue_prev_day"] is None else fmt_decimal(item["revenue_prev_day"]),
        "revenue_delta": "" if item["revenue_delta"] is None else fmt_decimal(item["revenue_delta"]),
        "revenue_delta_pct": fmt_percent(item["revenue_delta_pct"]),
        "category_spend_share": fmt_percent(item["category_spend_share"]),
        "ctr_vs_category_best": fmt_percent(item["ctr_vs_category_best"]),
        "cr1_vs_category_best": fmt_percent(item["cr1_vs_category_best"]),
        "cr2_vs_category_best": fmt_percent(item["cr2_vs_category_best"]),
        "orders_qty_mtd": fmt_int(item["orders_qty_mtd"]),
        "orders_rub_mtd": fmt_decimal(item["orders_rub_mtd"]),
        "plan_qty_completion_pct": fmt_percent(item["plan_qty_completion_pct"]),
        "plan_rub_completion_pct": fmt_percent(item["plan_rub_completion_pct"]),
        "forecast_qty_month": fmt_int(item["forecast_qty_month"]),
        "forecast_rub_month": fmt_decimal(item["forecast_rub_month"]),
        "forecast_qty_plan_pct": fmt_percent(item["forecast_qty_plan_pct"]),
        "forecast_rub_plan_pct": fmt_percent(item["forecast_rub_plan_pct"]),
        "oos_days_left": fmt_one(item["oos_days_left"]),
        "oos_risk": item["oos_risk"],
    }
    return "| " + " | ".join(values[header] for header in HEADERS) + " |"


def add_rows_table(lines, title, rows):
    lines.extend(
        [
            f"## {title}",
            "",
            "| " + " | ".join(HEADERS) + " |",
            "| " + " | ".join(["---"] * len(HEADERS)) + " |",
        ]
    )
    lines.extend(row_to_markdown(row) for row in rows)
    lines.append("")


def month_title(month_key: str, current_month_key: str, previous_month_key: str) -> str:
    if month_key == current_month_key:
        return f"Текущий месяц ({month_key})"
    if month_key == previous_month_key:
        return f"Предыдущий месяц ({month_key})"
    return f"Месяц {month_key}"


def build_markdown(rows, date_from: date, date_to: date, stock_date: date, calculation_from: date):
    total_impressions = sum((row["impressions"] for row in rows), Decimal("0"))
    total_clicks = sum((row["clicks"] for row in rows), Decimal("0"))
    total_orders = sum((row["orders_qty"] for row in rows), Decimal("0"))
    total_revenue = sum((row[REVENUE_KEY] for row in rows), Decimal("0"))
    total_spend = sum((row["ad_spend"] for row in rows), Decimal("0"))
    total_drr = pct(total_spend, total_revenue)

    current_month_key = date_to.strftime("%Y-%m")
    previous_month_date = month_start(date_to) - timedelta(days=1)
    previous_month_key = previous_month_date.strftime("%Y-%m")
    month_keys = sorted({row["month"] for row in rows}, reverse=True)

    lines = [
        "# WB: артикулярная выгрузка для сводки маркетолога",
        "",
        f"Период: **{date_from.isoformat()} - {date_to.isoformat()}**",
        "Гранулярность: **date + cabinet + sku**",
        "Фильтр: есть фин. выручка или траты РК; FBO используется только как справочная колонка.",
        f"Срез FBO: **{stock_date.isoformat()}**.",
        f"Расчет MTD-метрик: **с {calculation_from.isoformat()}**, с обнулением на границе месяца.",
        "",
        "---",
        "",
        "## Сводка",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
        f"| Строк | {fmt_int(len(rows))} |",
        f"| SKU | {fmt_int(len({row['sku'] for row in rows}))} |",
        f"| Кабинетов | {fmt_int(len({row['cabinet'] for row in rows}))} |",
        f"| Показы РК | {fmt_int(total_impressions)} |",
        f"| Клики РК | {fmt_int(total_clicks)} |",
        f"| Заказы WB | {fmt_int(total_orders)} |",
        f"| Фин. выручка | {fmt_decimal(total_revenue, zero_plain=False)} |",
        f"| Затраты РК | {fmt_decimal(total_spend, zero_plain=False)} |",
        f"| ДРР общий | {fmt_percent(total_drr)} |",
        "",
        "---",
        "",
        "## Добавленные метрики из ТЗ",
        "",
        "- `month`, `marketplace`, `ip`, `marketer`, `category`, `current_stock`.",
        "- `cpc`, `cpo`, `avg_price`, `plan_qty`, `plan_rub`, `plan_price`, `planned_drr`, `margin_rub`, `margin_percent`.",
        "- Динамика к предыдущему дню: `orders_delta`, `orders_delta_pct`, `revenue_delta`, `revenue_delta_pct`.",
        "- Категорийные индексы: `category_spend_share`, `ctr_vs_category_best`, `cr1_vs_category_best`, `cr2_vs_category_best`.",
        "- План/прогноз/OOS: `plan_*_completion_pct`, `forecast_*`, `oos_days_left`, `oos_risk`.",
        "",
        "---",
        "",
    ]

    if not rows:
        lines.extend(["## Текущий месяц", "", "Нет строк по заданному периоду.", ""])
        return "\n".join(lines)

    for month_key in month_keys:
        month_rows = [row for row in rows if row["month"] == month_key]
        add_rows_table(lines, month_title(month_key, current_month_key, previous_month_key), month_rows)
    return "\n".join(lines)


def aggregate_metrics(rows, key_fn):
    grouped = defaultdict(lambda: {"revenue": Decimal("0"), "ad_spend": Decimal("0")})
    for row in rows:
        key = key_fn(row)
        grouped[key]["revenue"] += row[REVENUE_KEY]
        grouped[key]["ad_spend"] += row["ad_spend"]
    return grouped


def display_message_name(value):
    return MESSAGE_NAME_REPLACEMENTS.get(str(value), str(value))


def display_ip_message_name(value):
    return IP_MESSAGE_NAME_REPLACEMENTS.get(str(value), display_message_name(value))


def metric_totals(rows):
    revenue = sum((row[REVENUE_KEY] for row in rows), Decimal("0"))
    spend = sum((row["ad_spend"] for row in rows), Decimal("0"))
    return {"revenue": revenue, "ad_spend": spend, "drr": pct(spend, revenue)}


def metric_values(values):
    values = values or {"revenue": Decimal("0"), "ad_spend": Decimal("0")}
    return {
        "revenue": values.get("revenue", Decimal("0")),
        "ad_spend": values.get("ad_spend", Decimal("0")),
        "drr": pct(values.get("ad_spend", Decimal("0")), values.get("revenue", Decimal("0"))),
    }


def drr_label(values):
    return fmt_percent(values.get("drr"), blank_if_none=False)


def spend_label(values):
    return fmt_rub(values.get("ad_spend", Decimal("0")))


def revenue_label(values):
    return fmt_rub(values.get("revenue", Decimal("0")))


def append_metric(lines, title, mtd_values, yesterday_values, day_before_values, formatter, emphasize=False):
    value = formatter(mtd_values)
    formatted_value = f"**`{value}`**" if emphasize else f"`{value}`"
    lines.append(f"• {title}: {formatted_value}")
    lines.append(f"• • вчера < позавчера: `{formatter(yesterday_values)}` < `{formatter(day_before_values)}`")


def category_marketer(category, rows):
    marketer_name = CATEGORY_MARKETER_NAMES.get(category)
    if marketer_name:
        return CATEGORY_MARKETER_MENTIONS.get(marketer_name, marketer_name)

    counts = defaultdict(int)
    for row in rows:
        marketer = str(row.get("marketer") or "").strip()
        if marketer and marketer != "-":
            counts[marketer] += 1
    if not counts:
        return "маркетолог не указан"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def build_niche_summaries(rows, date_to: date, stock_by_category=None):
    current_month_from = month_start(date_to)
    current_rows = [row for row in rows if current_month_from <= row["date"] <= date_to]
    stock_by_category = stock_by_category or {}
    days_in_month = Decimal(monthrange(date_to.year, date_to.month)[1])
    plan_factor = Decimal(date_to.day) / days_in_month

    grouped_rows = defaultdict(list)
    for row in current_rows:
        grouped_rows[str(row.get("category") or "Без ниши")].append(row)

    total_spend = sum((row["ad_spend"] for row in current_rows), Decimal("0"))
    summaries = []
    for category, category_rows in grouped_rows.items():
        revenue = sum((row[REVENUE_KEY] for row in category_rows), Decimal("0"))
        spend = sum((row["ad_spend"] for row in category_rows), Decimal("0"))
        orders = sum((row["orders_qty"] for row in category_rows), Decimal("0"))

        sku_actuals = defaultdict(lambda: {"revenue": Decimal("0"), "ad_spend": Decimal("0")})
        plan_by_sku = {}
        for row in category_rows:
            sku = str(row["sku"])
            sku_actuals[sku]["revenue"] += row[REVENUE_KEY]
            sku_actuals[sku]["ad_spend"] += row["ad_spend"]
            plan_key = (int(row["account_id"]), sku)
            plan_by_sku[plan_key] = {
                "plan_qty": row["plan_qty"],
                "plan_rub": row["plan_rub"],
                "planned_drr": row["planned_drr"],
            }

        active_skus = sum(
            1
            for values in sku_actuals.values()
            if values["revenue"] > ACTIVE_NICHE_SKU_THRESHOLD
            or values["ad_spend"] > ACTIVE_NICHE_SKU_THRESHOLD
        )
        if active_skus == 0:
            continue
        monthly_plan_revenue = sum((values["plan_rub"] for values in plan_by_sku.values()), Decimal("0"))
        monthly_plan_orders = sum((values["plan_qty"] for values in plan_by_sku.values()), Decimal("0"))
        monthly_plan_spend = sum(
            (
                values["plan_rub"] * values["planned_drr"] / Decimal("100")
                for values in plan_by_sku.values()
                if values["planned_drr"] > 0
            ),
            Decimal("0"),
        )
        drr_plan_revenue = sum(
            (values["plan_rub"] for values in plan_by_sku.values() if values["planned_drr"] > 0),
            Decimal("0"),
        )
        plan_revenue = monthly_plan_revenue * plan_factor
        plan_orders = monthly_plan_orders * plan_factor
        planned_drr = pct(monthly_plan_spend, drr_plan_revenue)
        actual_drr = pct(spend, revenue)
        revenue_completion = pct(revenue, plan_revenue)
        orders_completion = pct(orders, plan_orders)

        summaries.append(
            {
                "category": category,
                "season_type": NICHE_SEASON_TYPES.get(category, "unknown"),
                "marketer": category_marketer(category, category_rows),
                "active_skus": active_skus,
                "revenue": revenue,
                "plan_revenue": plan_revenue,
                "revenue_completion": revenue_completion,
                "spend": spend,
                "spend_share": pct(spend, total_spend),
                "actual_drr": actual_drr,
                "planned_drr": planned_drr,
                "orders": orders,
                "plan_orders": plan_orders,
                "orders_completion": orders_completion,
                "fbo": dec(stock_by_category.get(category)),
                "turnover_days": safe_div(
                    dec(stock_by_category.get(category)),
                    orders / Decimal(date_to.day) if orders else Decimal("0"),
                ),
            }
        )

    return sorted(summaries, key=lambda item: (-item["spend"], -item["revenue"], item["category"]))


def status_emoji(value, predicate):
    if value is None:
        return "⚪"
    return "🟢" if predicate(value) else "🔴"


def niche_statuses(summary):
    revenue_emoji = status_emoji(
        rounded_one(summary["revenue_completion"]),
        lambda value: value >= Decimal("90"),
    )
    if summary["actual_drr"] is None or summary["planned_drr"] is None:
        drr_emoji = "⚪"
    else:
        drr_emoji = (
            "🟢"
            if rounded_one(summary["actual_drr"]) <= rounded_one(summary["planned_drr"])
            else "🔴"
        )
    return revenue_emoji, drr_emoji


def append_marketer_summary(lines, summaries):
    by_marketer = defaultdict(list)
    for summary in summaries:
        by_marketer[summary["marketer"]].append(summary)

    lines.extend(["", "**Сводная по маркетологам**"])
    marketer_groups = sorted(
        by_marketer.items(),
        key=lambda item: (-sum((summary["spend"] for summary in item[1]), Decimal("0")), item[0]),
    )
    for marketer, marketer_summaries in marketer_groups:
        lines.extend(["", marketer])
        by_season = defaultdict(list)
        for summary in marketer_summaries:
            by_season[summary["season_type"]].append(summary)
        season_groups = sorted(
            by_season.items(),
            key=lambda item: SEASON_META[item[0]]["order"],
        )
        for season_type, season_summaries in season_groups:
            lines.append(f"**{SEASON_META[season_type]['summary'].upper()}**")
            for summary in season_summaries:
                revenue_emoji, drr_emoji = niche_statuses(summary)
                lines.append(f"• **{md_cell(summary['category'])} · {summary['active_skus']} SKU**")
                lines.append(
                    f"• • `Выручка {revenue_emoji} {fmt_percent_one(summary['revenue_completion'])}` · "
                    f"`ДРР {drr_emoji} {fmt_percent_one(summary['actual_drr'])} / "
                    f"{fmt_percent_one(summary['planned_drr'])}` · "
                    f"`💸 Доля трат {fmt_percent_one(summary['spend_share'])}` · "
                    f"`🔄 Оборачиваемость {fmt_days(summary['turnover_days'])}`"
                )


def build_niche_summary_message(rows, date_to: date, stock_by_category=None):
    current_month_from = month_start(date_to)
    summaries = build_niche_summaries(rows, date_to, stock_by_category)
    lines = [
        "**WB: показатели по нишам**",
        f"`{fmt_date(current_month_from)}–{fmt_date(date_to)} · факт / план`",
        "`SKU: выручка или траты MTD > 5 тыс. ₽`",
    ]
    if not summaries:
        lines.extend(["", "Нет данных за текущий месяц."])
        return "\n".join(lines)

    append_marketer_summary(lines, summaries)
    return "\n".join(lines)


def build_niche_detail_message(rows, date_to: date, stock_by_category=None):
    current_month_from = month_start(date_to)
    summaries = build_niche_summaries(rows, date_to, stock_by_category)
    lines = [
        "**Детализация по нишам**",
        f"`{fmt_date(current_month_from)}–{fmt_date(date_to)} · факт / план`",
    ]
    if not summaries:
        lines.extend(["", "Нет данных за текущий месяц."])
        return "\n".join(lines)

    for summary in summaries:
        revenue_emoji, drr_emoji = niche_statuses(summary)
        lines.extend(
            [
                "",
                f"**{md_cell(summary['category'])} · "
                f"{SEASON_META[summary['season_type']]['detail']} · "
                f"{summary['active_skus']} SKU** · {summary['marketer']}",
                f"`Выручка {revenue_emoji}` · `ДРР {drr_emoji}` · `💸 Доля трат {fmt_percent_one(summary['spend_share'])}`",
                f"• 💰 Выручка `{fmt_percent_one(summary['revenue_completion'])}` — "
                f"`{fmt_compact_pair(summary['revenue'], summary['plan_revenue'], currency=True)}`",
                f"• 🎯 ДРР `{fmt_percent_one(summary['actual_drr'])} / {fmt_percent_one(summary['planned_drr'])}` "
                f"— траты `{fmt_compact_value(summary['spend'], currency=True)}`",
                f"• 🛒 Заказы `{fmt_percent_one(summary['orders_completion'])}` — "
                f"`{fmt_compact_pair(summary['orders'], summary['plan_orders'])}`",
                f"• 📦 FBO `{fmt_int(summary['fbo'])} шт.` — "
                f"`{fmt_days(summary['turnover_days'])}`",
            ]
        )
    return "\n".join(lines)


def build_message(rows, date_from: date, date_to: date):
    current_month_from = month_start(date_to)
    current_rows = [row for row in rows if current_month_from <= row["date"] <= date_to]
    yesterday = date_to
    day_before = date_to - timedelta(days=1)
    yesterday_rows = [row for row in rows if row["date"] == yesterday]
    day_before_rows = [row for row in rows if row["date"] == day_before]
    total_mtd = metric_totals(current_rows)
    total_yesterday = metric_totals(yesterday_rows)
    total_day_before = metric_totals(day_before_rows)
    ip_mtd = aggregate_metrics(current_rows, lambda row: row["ip"])
    ip_yesterday = aggregate_metrics(yesterday_rows, lambda row: row["ip"])
    ip_day_before = aggregate_metrics(day_before_rows, lambda row: row["ip"])
    cabinet_mtd = aggregate_metrics(current_rows, lambda row: row["cabinet"])
    cabinet_yesterday = aggregate_metrics(yesterday_rows, lambda row: row["cabinet"])
    cabinet_day_before = aggregate_metrics(day_before_rows, lambda row: row["cabinet"])
    output_days = (date_to - date_from).days + 1

    lines = [
        "**WB: отчет для сводки маркетолога**",
        f"`{REPORT_RUN_LABEL}`",
        "",
        f"**Период файла:** {fmt_date(date_from)} - {fmt_date(date_to)} ({output_days} дн.)",
        f"**ДРР с начала месяца:** {fmt_date(current_month_from)} - {fmt_date(date_to)}",
        "",
        "**WB общий**",
    ]
    append_metric(lines, "ДРР", total_mtd, total_yesterday, total_day_before, drr_label, emphasize=True)
    append_metric(lines, "Траты РК", total_mtd, total_yesterday, total_day_before, spend_label)
    append_metric(lines, "Выручка", total_mtd, total_yesterday, total_day_before, revenue_label)
    lines.extend(["", "**ДРР MTD по ИП**"])
    if not ip_mtd:
        lines.append("Нет данных за текущий месяц.")
    for ip, values in sorted(
        ip_mtd.items(),
        key=lambda item: (IP_MESSAGE_ORDER.get(item[0], 100), display_ip_message_name(item[0])),
    ):
        lines.append("")
        lines.append(f"**{display_ip_message_name(ip)}**")
        append_metric(
            lines,
            "ДРР",
            metric_values(values),
            metric_values(ip_yesterday.get(ip)),
            metric_values(ip_day_before.get(ip)),
            drr_label,
            emphasize=True,
        )
        append_metric(
            lines,
            "Траты РК",
            metric_values(values),
            metric_values(ip_yesterday.get(ip)),
            metric_values(ip_day_before.get(ip)),
            spend_label,
        )
        append_metric(
            lines,
            "Выручка",
            metric_values(values),
            metric_values(ip_yesterday.get(ip)),
            metric_values(ip_day_before.get(ip)),
            revenue_label,
        )
    lines.extend(["", "**ДРР MTD по кабинетам**"])
    if not cabinet_mtd:
        lines.append("Нет данных за текущий месяц.")
    for cabinet, values in sorted(
        cabinet_mtd.items(),
        key=lambda item: (CABINET_MESSAGE_ORDER.get(item[0], 100), display_message_name(item[0])),
    ):
        lines.append("")
        lines.append(f"**{display_message_name(cabinet)}**")
        append_metric(
            lines,
            "ДРР",
            metric_values(values),
            metric_values(cabinet_yesterday.get(cabinet)),
            metric_values(cabinet_day_before.get(cabinet)),
            drr_label,
            emphasize=True,
        )
        append_metric(
            lines,
            "Траты РК",
            metric_values(values),
            metric_values(cabinet_yesterday.get(cabinet)),
            metric_values(cabinet_day_before.get(cabinet)),
            spend_label,
        )
        append_metric(
            lines,
            "Выручка",
            metric_values(values),
            metric_values(cabinet_yesterday.get(cabinet)),
            metric_values(cabinet_day_before.get(cabinet)),
            revenue_label,
        )
    lines.extend(["", "_Markdown-файл с таблицами приложен к сообщению._"])
    return "\n".join(lines)


def build_summary(rows, message_rows, date_from: date, date_to: date, stock_date: date):
    total_revenue = sum((row[REVENUE_KEY] for row in rows), Decimal("0"))
    total_spend = sum((row["ad_spend"] for row in rows), Decimal("0"))
    current_month_from = month_start(date_to)
    current_rows = [row for row in message_rows if current_month_from <= row["date"] <= date_to]
    current_revenue = sum((row[REVENUE_KEY] for row in current_rows), Decimal("0"))
    current_spend = sum((row["ad_spend"] for row in current_rows), Decimal("0"))
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "stock_date": stock_date.isoformat(),
        "rows": len(rows),
        "skus": len({row["sku"] for row in rows}),
        "cabinets": len({row["cabinet"] for row in rows}),
        "revenue": str(total_revenue),
        "ad_spend": str(total_spend),
        "drr": str(pct(total_spend, total_revenue) or Decimal("0")),
        "current_month_revenue": str(current_revenue),
        "current_month_ad_spend": str(current_spend),
        "current_month_drr": str(pct(current_spend, current_revenue) or Decimal("0")),
    }


def parse_args():
    default_date_to = os.getenv("REPORT_DATE_TO")
    default_date_from = os.getenv("REPORT_DATE_FROM")
    default_stock_date = os.getenv("REPORT_STOCK_DATE")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", default=default_date_from)
    parser.add_argument("--date-to", default=default_date_to)
    parser.add_argument("--stock-date", default=default_stock_date)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--out-dir", default=os.getenv("REPORT_OUT_DIR", str(ROOT)))
    return parser.parse_args()


def main():
    args = parse_args()
    date_to = parse_date(args.date_to) if args.date_to else today() - timedelta(days=1)
    date_from = parse_date(args.date_from) if args.date_from else date_to - timedelta(days=args.window_days - 1)
    requested_stock_date = parse_date(args.stock_date) if args.stock_date else date_to + timedelta(days=1)
    calculation_from = month_start(date_from)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    old_ip_by_sku = load_old_ip_by_sku(OLD_IP_REPORT_PATH)
    db = McpSql()
    try:
        stock_date = resolve_stock_date(db, requested_stock_date)
        raw_rows = query_rows(db, calculation_from, date_to, stock_date)
        niche_stocks = query_niche_stocks(db, stock_date)
    finally:
        db.close()

    calculation_rows = enrich_rows(raw_rows, calculation_from, old_ip_by_sku)
    output_rows = [row for row in calculation_rows if date_from <= row["date"] <= date_to]

    report_name = f"wb_articles_marketer_metrics_30d_{date_from.isoformat()}_{date_to.isoformat()}"
    md_path = out_dir / f"{report_name}.md"
    message_path = out_dir / f"{report_name}_message.md"
    niche_message_path = out_dir / f"{report_name}_niches.md"
    niche_thread_message_path = out_dir / f"{report_name}_niches_thread.md"
    summary_path = out_dir / f"{report_name}.json"

    md_path.write_text(build_markdown(output_rows, date_from, date_to, stock_date, calculation_from), encoding="utf-8")
    message_path.write_text(build_message(calculation_rows, date_from, date_to), encoding="utf-8")
    niche_message_path.write_text(
        build_niche_summary_message(calculation_rows, date_to, niche_stocks),
        encoding="utf-8",
    )
    niche_thread_message_path.write_text(
        build_niche_detail_message(calculation_rows, date_to, niche_stocks),
        encoding="utf-8",
    )

    summary = build_summary(output_rows, calculation_rows, date_from, date_to, stock_date)
    summary.update(
        {
            "md": str(md_path),
            "message": str(message_path),
            "niche_message": str(niche_message_path),
            "niche_thread_message": str(niche_thread_message_path),
            "niches": len(build_niche_summaries(calculation_rows, date_to, niche_stocks)),
            "summary_json": str(summary_path),
        }
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
