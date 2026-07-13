#!/usr/bin/env python3
"""Товарная аналитика ниш для ежедневного отчёта в Пачку."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median


ACTIVE_SKU_THRESHOLD = Decimal("5000")
FBO_SPEND_ACTIVE_THRESHOLD = Decimal("300")
RECENT_PRICE_DAYS = 2
CRM_HORIZON_DAYS = 60
POSITION_FRESHNESS_DAYS = 2


def dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def pct(numerator, denominator):
    numerator_value = dec(numerator)
    denominator_value = dec(denominator)
    if denominator_value == 0:
        return None
    return numerator_value / denominator_value * Decimal("100")


def ratio_days(stock, daily_orders):
    stock_value = dec(stock)
    daily_value = dec(daily_orders)
    if daily_value > 0:
        return stock_value / daily_value
    return Decimal("9999") if stock_value > 0 else None


def key_predicate(alias: str, pairs: set[tuple[int, str]]) -> str:
    by_account = defaultdict(list)
    for account_id, sku in pairs:
        if str(sku).isdigit():
            by_account[int(account_id)].append(str(int(sku)))
    parts = []
    for account_id, skus in sorted(by_account.items()):
        parts.append(
            f"({alias}.account_id = {account_id} AND CAST({alias}.sku AS UNSIGNED) IN "
            f"({','.join(sorted(set(skus), key=int))}))"
        )
    return " OR ".join(parts) or "1 = 0"


def card_predicate(alias: str, card_keys: set[tuple[int, int]]) -> str:
    by_account = defaultdict(list)
    for account_id, card_id in card_keys:
        by_account[int(account_id)].append(str(int(card_id)))
    parts = []
    for account_id, card_ids in sorted(by_account.items()):
        parts.append(
            f"({alias}.account_id = {account_id} AND {alias}.card_id IN "
            f"({','.join(sorted(set(card_ids), key=int))}))"
        )
    return " OR ".join(parts) or "1 = 0"


def query_card_meta(db, active_pairs):
    predicate = key_predicate("card", active_pairs)
    rows = db.query(
        f"""
        SELECT card.account_id,
               MAX(card.card_id) AS card_id,
               CAST(card.sku AS CHAR) AS sku,
               MAX(card.crm_id) AS crm_id,
               MAX(card.card_short_name) AS product_name
        FROM dbt.mp_core__card_all card
        WHERE LOWER(card.mp) = 'wb'
          AND ({predicate})
        GROUP BY card.account_id, CAST(card.sku AS CHAR);
        """
    )
    return {
        (int(row["account_id"]), str(row["sku"])): {
            "card_id": int(row.get("card_id") or 0),
            "crm_id": int(row.get("crm_id") or 0),
            "product_name": str(row.get("product_name") or "-"),
        }
        for row in rows
    }


def query_margins(db, card_keys, date_from, date_to):
    predicate = card_predicate("fact", card_keys)
    rows = db.query(
        f"""
        SELECT fact.account_id, fact.card_id,
               SUM(COALESCE(fact.revenue, 0)) AS revenue,
               SUM(COALESCE(fact.margin_ds, 0)) AS margin_before_ads,
               SUM(COALESCE(fact.margin_ds_with_advert, 0)) AS margin_after_ads,
               SUM(COALESCE(fact.advert_spent, 0)) AS advert_spent
        FROM dbt.mp_core__realtime_full_new fact
        WHERE LOWER(fact.mp) = 'wb'
          AND fact.date BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'
          AND ({predicate})
        GROUP BY fact.account_id, fact.card_id;
        """
    )
    return {
        (int(row["account_id"]), int(row["card_id"])): {
            "margin_before_ads": dec(row.get("margin_before_ads")),
            "margin_after_ads": dec(row.get("margin_after_ads")),
            "margin_revenue": dec(row.get("revenue")),
            "margin_ad_spend": dec(row.get("advert_spent")),
        }
        for row in rows
    }


def query_prices(db, card_keys, current_date):
    predicate = card_predicate("price", card_keys)
    date_from = current_date - timedelta(days=7)
    rows = db.query(
        f"""
        SELECT price.account_id, price.card_id, price.date,
               MAX(COALESCE(price.price, 0)) AS price_before_spp,
               MAX(NULLIF(price.price_mp, 0)) AS price_with_spp,
               MAX(NULLIF(price.discount_mp, -1)) AS spp_percent
        FROM mp.mp_core__realtime_prices price
        WHERE LOWER(price.mp) = 'wb'
          AND price.date BETWEEN '{date_from.isoformat()}' AND '{current_date.isoformat()}'
          AND ({predicate})
        GROUP BY price.account_id, price.card_id, price.date
        ORDER BY price.account_id, price.card_id, price.date;
        """
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[(int(row["account_id"]), int(row["card_id"]))].append(row)
    result = {}
    for key, values in grouped.items():
        values.sort(key=lambda row: str(row.get("date"))[:10])
        last_increase_date = None
        for previous, current in zip(values, values[1:]):
            if dec(current.get("price_before_spp")) > dec(previous.get("price_before_spp")):
                last_increase_date = str(current.get("date"))[:10]
        latest = values[-1]
        previous = values[-2] if len(values) > 1 else latest
        result[key] = {
            "price_before_spp": dec(latest.get("price_before_spp")),
            "price_with_spp": dec(latest.get("price_with_spp")),
            "spp_percent": dec(latest.get("spp_percent")),
            "previous_price_before_spp": dec(previous.get("price_before_spp")),
            "price_date": str(latest.get("date"))[:10],
            "last_price_increase_date": last_increase_date,
        }
    return result


def query_reviews(db, card_keys, current_date):
    selected_rows = " UNION ALL ".join(
        f"SELECT {int(account_id)} AS account_id, {int(card_id)} AS card_id"
        for account_id, card_id in sorted(card_keys)
    ) or "SELECT 0 AS account_id, 0 AS card_id"
    rows = db.query(
        f"""
        WITH selected_cards AS (
            {selected_rows}
        ), ranked AS (
            SELECT selected.account_id, review.card_id, review.date,
                   review.rating, review.total_reviews,
                   ROW_NUMBER() OVER (
                       PARTITION BY selected.account_id, review.card_id
                       ORDER BY review.date DESC
                   ) AS rn
            FROM selected_cards selected
            JOIN mp.mp_core__review_rating review
              ON review.card_id = selected.card_id
            WHERE LOWER(review.mp) = 'wb'
              AND review.date <= '{current_date.isoformat()}'
        )
        SELECT account_id, card_id, date, rating, total_reviews
        FROM ranked
        WHERE rn = 1;
        """
    )
    return {
        (int(row["account_id"]), int(row["card_id"])): {
            "rating": dec(row.get("rating")),
            "reviews": int(dec(row.get("total_reviews"))),
            "review_date": str(row.get("date"))[:10],
        }
        for row in rows
    }


def query_crm_incoming(db, crm_ids, current_date):
    if not crm_ids:
        return {}
    incoming_to = current_date + timedelta(days=CRM_HORIZON_DAYS)
    rows = db.query(
        f"""
        SELECT orders.crm_id,
               SUM(COALESCE(orders.wb_count, orders.count, 0)) AS incoming_qty,
               MIN(orders.date) AS nearest_incoming_date
        FROM dbt.crm__orders orders
        WHERE orders.crm_id IN ({','.join(str(value) for value in sorted(crm_ids))})
          AND orders.date BETWEEN '{current_date.isoformat()}' AND '{incoming_to.isoformat()}'
          AND COALESCE(orders.status_correct, '') <> 'Принят'
        GROUP BY orders.crm_id;
        """
    )
    return {
        int(row["crm_id"]): {
            "incoming_qty": dec(row.get("incoming_qty")),
            "nearest_incoming_date": str(row.get("nearest_incoming_date") or "")[:10],
        }
        for row in rows
    }


def query_campaign_mechanics(db, active_pairs, date_from, date_to):
    predicate = key_predicate("stat", active_pairs)
    rows = db.query(
        f"""
        SELECT stat.account_id, CAST(stat.sku AS CHAR) AS sku,
               CASE
                   WHEN LOWER(COALESCE(campaign.bid_type, '')) = 'unified' THEN 'Единая ставка'
                   WHEN LOWER(COALESCE(campaign.payment_type, '')) = 'cpc' THEN 'Оплата за клики'
                   ELSE 'Ручная ставка'
               END AS mechanic,
               SUM(COALESCE(stat.consumptions, 0)) AS spend,
               SUM(COALESCE(stat.orders_money, 0)) AS ad_revenue,
               SUM(COALESCE(stat.impressions, 0)) AS impressions,
               SUM(COALESCE(stat.clicks, 0)) AS clicks
        FROM mp.wb_core__campaign_stat_daily_sku stat
        LEFT JOIN mp.wb_core__campaign campaign
          ON campaign.account_id = stat.account_id
         AND campaign.campaign_id = stat.campaign_id
        WHERE stat.date_at BETWEEN '{date_from.isoformat()}' AND '{date_to.isoformat()}'
          AND ({predicate})
        GROUP BY stat.account_id, CAST(stat.sku AS CHAR), mechanic;
        """
    )
    result = defaultdict(list)
    for row in rows:
        spend = dec(row.get("spend"))
        ad_revenue = dec(row.get("ad_revenue"))
        impressions = dec(row.get("impressions"))
        clicks = dec(row.get("clicks"))
        result[(int(row["account_id"]), str(row["sku"]))].append(
            {
                "mechanic": str(row.get("mechanic") or "Ручная ставка"),
                "spend": spend,
                "ad_revenue": ad_revenue,
                "drr": pct(spend, ad_revenue),
                "ctr": pct(clicks, impressions),
                "cpc": spend / clicks if clicks else None,
            }
        )
    for values in result.values():
        values.sort(key=lambda item: item["spend"], reverse=True)
    return result


def query_positions(db, skus, current_date):
    latest_rows = db.query(
        f"""
        SELECT MAX(date_at) AS latest_date
        FROM mp.wb_core__mps_group_stat
        WHERE date_at <= '{current_date.isoformat()}';
        """
    )
    latest_text = str((latest_rows or [{}])[0].get("latest_date") or "")[:10]
    if not latest_text:
        return {}, None, False
    latest_date = date.fromisoformat(latest_text)
    if (current_date - latest_date).days > POSITION_FRESHNESS_DAYS:
        return {}, latest_date, False
    numeric_skus = sorted({str(int(sku)) for sku in skus if str(sku).isdigit()}, key=int)
    if not numeric_skus:
        return {}, latest_date, True
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku, position,
               search_position_avg, search_ad_position_avg,
               search_organic_position_avg, category_position_avg
        FROM mp.wb_core__mps_group_stat
        WHERE date_at = '{latest_date.isoformat()}'
          AND CAST(sku AS UNSIGNED) IN ({','.join(numeric_skus)});
        """
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row["sku"])].append(row)
    result = {}
    for sku, values in grouped.items():
        raw_positions = [float(row["position"]) for row in values if row.get("position") not in (None, "")]

        def average(field):
            present = [dec(row.get(field)) for row in values if row.get(field) not in (None, "")]
            return sum(present, Decimal("0")) / len(present) if present else None

        result[sku] = {
            "search_position": average("search_position_avg"),
            "ad_position": average("search_ad_position_avg"),
            "organic_position": average("search_organic_position_avg"),
            "category_position": average("category_position_avg"),
            "median_keyword_position": Decimal(str(median(raw_positions))) if raw_positions else None,
        }
    return result, latest_date, True


def load_fbo_supply_confirmation(candidate_skus, current_date):
    if not candidate_skus:
        return {}, True
    try:
        from build_sheet_supplies_md import (
            load_supply_sheet_rows,
            parse_sheet_date,
            parse_wb_article,
            to_int,
        )

        rows = load_supply_sheet_rows()
    except Exception:
        return {}, False

    end_date = current_date + timedelta(days=5)
    result = defaultdict(lambda: {"confirmed": False, "nearest_date": "", "qty": Decimal("0")})
    for row in rows:
        if len(row) < 13:
            continue
        row_date = parse_sheet_date(row[0])
        if not row_date or not (current_date <= row_date <= end_date):
            continue
        product_text = str(row[9] or "")
        barcode = str(row[11] or "")
        sku = parse_wb_article(product_text, barcode)
        if sku not in candidate_skus:
            continue
        qty = dec(to_int(row[12]))
        if qty <= 0:
            continue
        item = result[sku]
        item["confirmed"] = True
        item["qty"] += qty
        if not item["nearest_date"] or row_date.isoformat() < item["nearest_date"]:
            item["nearest_date"] = row_date.isoformat()
    return dict(result), True


def priority(score, growth=False):
    if score >= 65:
        return {"code": "P1", "label": "Критично", "rank": 1}
    if score >= 45:
        return {"code": "P2", "label": "Высокий", "rank": 2}
    if growth:
        return {"code": "G", "label": "Рост", "rank": 4}
    if score >= 20:
        return {"code": "P3", "label": "Средний", "rank": 3}
    return {"code": "P4", "label": "Низкий", "rank": 5}


def product_decision(row):
    drr_over = Decimal("0")
    if row["drr"] is not None:
        drr_over = row["drr"] - row["drr_plan"] if row["drr_plan"] is not None else row["drr"]
    eligible = [item for item in row["mechanics"] if item["spend"] >= FBO_SPEND_ACTIVE_THRESHOLD]
    profitable = [item for item in eligible if item["drr"] is not None]
    best = min(profitable, key=lambda item: item["drr"], default=None)
    worst = max(eligible, key=lambda item: item["drr"] if item["drr"] is not None else Decimal("9999"), default=None)
    turnover = row["turnover_days"]
    future_days = row["future_stock_days"]
    stock_pressure = (
        (turnover is not None and turnover > 60)
        or (future_days is not None and future_days > 90)
        or row["incoming_qty"] > max(Decimal("100"), row["fbo_stock"] * Decimal("0.3"))
    )
    under_plan = row["revenue_plan"] > 0 and row["plan_pct"] is not None and row["plan_pct"] < 90
    strong_over = row["revenue_plan"] > 0 and row["plan_pct"] is not None and row["plan_pct"] >= 120
    efficient = row["drr_plan"] is not None and row["drr"] is not None and row["drr"] <= row["drr_plan"]
    low_three = turnover is not None and turnover <= 3
    low_five = turnover is not None and Decimal("3") < turnover <= 5
    weak_card = (row["rating"] > 0 and row["rating"] < Decimal("4.5")) or (0 < row["reviews"] < 200)
    issue = "Критичных отклонений нет"
    action = "Сохранить настройки; контролировать выручку, ДРР и остаток."
    methods = ["Наблюдение"]

    if low_three:
        issue = f"FBO {turnover:.1f} дн.; расход вчера {row['yesterday_spend']:.0f} ₽"
        if row["yesterday_spend"] < FBO_SPEND_ACTIVE_THRESHOLD:
            action = "РК уже фактически неактивна; дополнительных действий по рекламе нет."
        elif row["seasonal"]:
            action = "Сезонный товар: РК не выключать; цену одновременно не менять."
        else:
            action = "Выключить РК из-за FBO ≤3 дней; цену одновременно не менять."
        methods = ["FBO"]
    elif low_five and row["yesterday_spend"] >= FBO_SPEND_ACTIVE_THRESHOLD:
        issue = f"FBO {turnover:.1f} дн.; расход вчера {row['yesterday_spend']:.0f} ₽"
        if not row["fbo_supply_checked"]:
            action = "Поставка Google не проверена; решение по сокращению РК не назначать до проверки."
            methods = ["FBO", "Наблюдение"]
        elif row["fbo_supply_confirmed"]:
            action = "Поставка подтверждена в 5 дней; сохранить РК и контролировать фактический FBO."
            methods = ["FBO", "Наблюдение"]
        elif row["recent_price_increase"]:
            action = "Не делать резкое второе изменение: зафиксировать цену, затем ступенчато сократить худшую механику."
            methods = ["FBO", "Цена", "Реклама"]
        else:
            action = "Сократить расход худшей механики РК; цену одновременно не менять."
            methods = ["FBO", "Реклама"]
    elif row["recent_price_increase"] and drr_over > Decimal("0.5"):
        issue = f"Цена повышена {row['last_price_increase_date']}; ДРР выше плана на {drr_over:.1f} п.п."
        action = "Не сокращать РК 2–3 дня; зафиксировать цену и расход, затем менять только худшую механику."
        methods = ["Цена", "Реклама", "Наблюдение"]
    elif drr_over > Decimal("0.5"):
        issue = (
            f"ДРР {row['drr']:.1f}% при плане {row['drr_plan']:.1f}%"
            if row["drr_plan"] is not None
            else "Есть расход РК, но план ДРР не задан"
        )
        if worst:
            verb = "Выключить/резко сократить" if worst["drr"] is None or worst["drr"] > max((row["drr_plan"] or 0) * 2, Decimal("25")) else "Сократить"
            action = f"{verb} «{worst['mechanic']}»"
            if best and best["mechanic"] != worst["mechanic"]:
                action += f"; сохранить «{best['mechanic']}» как основную."
            else:
                action += "; цену одновременно не менять."
        else:
            action = "Ограничить общий расход РК и задать план ДРР; цену одновременно не менять."
        methods = ["Реклама"] + (["Экономика"] if row["margin_pre_pct"] < 0 else [])
    elif under_plan and stock_pressure:
        issue = f"План {row['plan_pct']:.1f}%; запас с CRM {future_days:.1f} дн." if future_days is not None else f"План {row['plan_pct']:.1f}%; есть давление стока"
        if not row["margin_available"]:
            action = "Ускорить продажу через карточку и эффективную РК; цену не тестировать до получения маржинальности."
        elif row["margin_post_pct"] > 0 and best and not row["recent_price_increase"]:
            action = f"Ускорить продажу: увеличить «{best['mechanic']}» на 10–15%, усилить оффер; цену тестировать отдельно после расчёта маржи."
        elif row["margin_post_pct"] > 0 and row["recent_price_increase"]:
            action = "Ускоренная продажа нужна, но цена повышена недавно: сохранить рекламную поддержку и оценить реакцию 2–3 дня."
        else:
            action = "Ускорить продажу через карточку/оффер и эффективную РК; снижение цены заблокировано отрицательной маржой."
        methods = ["Ускоренная продажа", "Карточка"] + (["Реклама"] if best else []) + (["Экономика"] if row["margin_post_pct"] <= 0 else [])
    elif strong_over and efficient and row["margin_available"] and row["margin_post_pct"] > 0 and turnover is not None and turnover > 14:
        issue = f"План {row['plan_pct']:.1f}%; ДРР в плане; маржа после РК {row['margin_post_pct']:.1f}%"
        if row["recent_price_increase"]:
            action = "Потенциал роста есть: не урезать РК, выдержать 2–3 дня после повышения цены."
            methods = ["Реклама", "Цена", "Наблюдение"]
        elif best:
            action = f"Масштабировать «{best['mechanic']}» на 10–15%, контролируя маржу и FBO."
            methods = ["Реклама"]
        else:
            action = "Запустить ограниченный тест РК без одновременного изменения цены."
            methods = ["Реклама"]
    elif row["margin_available"] and (row["margin_pre_pct"] < 0 or row["margin_post_pct"] < 0):
        issue = f"Маржа до РК {row['margin_pre_pct']:.1f}%, после РК {row['margin_post_pct']:.1f}%"
        action = "Проверить себестоимость, комиссию и логистику; снижение цены и масштабирование РК заблокировать."
        methods = ["Экономика", "Цена"]
    elif weak_card and (under_plan or drr_over > 0):
        issue = f"Карточка: рейтинг {row['rating'] or '—'}, отзывы {row['reviews'] or '—'}"
        action = "Исправить карточку и негатив в отзывах; рекламу не масштабировать до улучшения конверсии."
        methods = ["Карточка"]
    elif strong_over and efficient:
        issue = f"План {row['plan_pct']:.1f}%; ДРР в плане"
        action = "Проверить потенциал роста лучшей механики РК; менять расход отдельно от цены."
        methods = ["Реклама"]

    score = Decimal("0")
    if row["revenue_plan"] > 0 and row["plan_pct"] is not None:
        score += 30 if row["plan_pct"] < 50 else 22 if row["plan_pct"] < 70 else 12 if row["plan_pct"] < 90 else 0
    score += 30 if drr_over > 10 else 20 if drr_over > 5 else 10 if drr_over > Decimal("0.5") else 0
    if row["margin_available"]:
        score += 25 if row["margin_pre_pct"] < -20 else 15 if row["margin_pre_pct"] < 0 else 0
        score += 10 if row["margin_post_pct"] < 0 else 0
    score += 25 if turnover is not None and turnover > 150 else 18 if turnover is not None and turnover > 90 else 10 if turnover is not None and turnover > 60 else 0
    score += 15 if future_days is not None and future_days > 150 else 8 if future_days is not None and future_days > 90 else 0
    score += 15 if low_three and row["yesterday_spend"] >= FBO_SPEND_ACTIVE_THRESHOLD else 0
    score += 6 if weak_card else 0
    score += 8 if row["recent_price_increase"] and drr_over > Decimal("0.5") else 0
    growth = strong_over and efficient and row["margin_available"] and row["margin_post_pct"] > 0 and turnover is not None and turnover > 14
    return {
        "issue": issue,
        "action": action,
        "methods": list(dict.fromkeys(methods)),
        "score": min(int(score), 100),
        "priority": priority(int(score), growth),
        "growth": growth,
    }


def load_product_analytics(db, rows, date_to):
    date_from = date_to.replace(day=1)
    current_date = date_to + timedelta(days=1)
    covered_days = Decimal(date_to.day)
    plan_factor = Decimal(date_to.day) / Decimal(monthrange(date_to.year, date_to.month)[1])
    grouped = defaultdict(list)
    for row in rows:
        if date_from <= row["date"] <= date_to:
            grouped[(int(row["account_id"]), str(row["sku"]))].append(row)

    active = {}
    for key, values in grouped.items():
        revenue = sum((dec(row.get("finance_revenue")) for row in values), Decimal("0"))
        spend = sum((dec(row.get("ad_spend")) for row in values), Decimal("0"))
        if revenue <= ACTIVE_SKU_THRESHOLD and spend <= ACTIVE_SKU_THRESHOLD:
            continue
        latest = max(values, key=lambda row: row["date"])
        active[key] = {
            "rows": values,
            "revenue": revenue,
            "ad_spend": spend,
            "orders": sum((dec(row.get("orders_qty")) for row in values), Decimal("0")),
            "plan_monthly": dec(latest.get("plan_rub")),
            "drr_plan": dec(latest.get("planned_drr")) or None,
            "category": str(latest.get("category") or "Без ниши"),
            "product_name": str(latest.get("product_name") or "-"),
            "marketer": str(latest.get("marketer") or "-"),
            "fbo_stock": max((dec(row.get("current_stock")) for row in values), default=Decimal("0")),
            "yesterday_spend": sum((dec(row.get("ad_spend")) for row in values if row["date"] == date_to), Decimal("0")),
            "yesterday_revenue": sum((dec(row.get("finance_revenue")) for row in values if row["date"] == date_to), Decimal("0")),
        }

    active_pairs = set(active)
    if not active_pairs:
        return {"products": [], "position_source_date": None, "positions_fresh": False, "fbo_supply_checked": True}

    card_meta = query_card_meta(db, active_pairs)
    card_keys = {
        (account_id, meta["card_id"])
        for (account_id, _sku), meta in card_meta.items()
        if meta["card_id"]
    }
    margins = query_margins(db, card_keys, date_from, date_to)
    prices = query_prices(db, card_keys, current_date)
    reviews = query_reviews(db, card_keys, current_date)
    mechanics = query_campaign_mechanics(db, active_pairs, date_from, date_to)
    crm_ids = {meta["crm_id"] for meta in card_meta.values() if meta["crm_id"]}
    incoming = query_crm_incoming(db, crm_ids, current_date)
    positions, position_source_date, positions_fresh = query_positions(
        db,
        {sku for _account_id, sku in active_pairs},
        current_date,
    )

    products = []
    recent_boundary = current_date - timedelta(days=RECENT_PRICE_DAYS)
    for (account_id, sku), base in active.items():
        meta = card_meta.get((account_id, sku), {"card_id": 0, "crm_id": 0, "product_name": base["product_name"]})
        card_key = (account_id, meta["card_id"])
        margin = margins.get(card_key, {})
        price = prices.get(card_key, {})
        review = reviews.get(card_key, {})
        crm = incoming.get(meta["crm_id"], {})
        daily_orders = base["orders"] / covered_days if covered_days else Decimal("0")
        turnover_days = ratio_days(base["fbo_stock"], daily_orders)
        incoming_qty = dec(crm.get("incoming_qty"))
        future_stock_days = ratio_days(base["fbo_stock"] + incoming_qty, daily_orders)
        revenue_plan = base["plan_monthly"] * plan_factor
        margin_before = dec(margin.get("margin_before_ads"))
        margin_after = dec(margin.get("margin_after_ads"))
        last_increase_text = str(price.get("last_price_increase_date") or "")
        last_increase = date.fromisoformat(last_increase_text) if last_increase_text else None
        product = {
            "account_id": account_id,
            "card_id": meta["card_id"],
            "crm_id": meta["crm_id"],
            "sku": sku,
            "category": base["category"],
            "product_name": meta.get("product_name") or base["product_name"],
            "marketer": base["marketer"],
            "seasonal": base["category"] in {
                "Аксессуары для бассейна", "Бассейны каркасные", "Бассейны надувные", "Колготки",
                "Колготки для малышей", "Комплекты садовой мебели", "Круги для плавания",
                "Лестницы для бассейнов", "Матрасы для плавания", "Одеяла", "Опрыскиватели",
                "Походный душ", "Светильники уличные", "Скиммеры", "Столы туристические",
                "Стулья", "Тенты для бассейнов", "Шатры и беседки",
            },
            "revenue": base["revenue"],
            "revenue_plan": revenue_plan,
            "plan_pct": pct(base["revenue"], revenue_plan),
            "ad_spend": base["ad_spend"],
            "drr": pct(base["ad_spend"], base["revenue"]),
            "drr_plan": base["drr_plan"],
            "orders": base["orders"],
            "yesterday_spend": base["yesterday_spend"],
            "yesterday_drr": pct(base["yesterday_spend"], base["yesterday_revenue"]),
            "fbo_stock": base["fbo_stock"],
            "turnover_days": turnover_days,
            "incoming_qty": incoming_qty,
            "nearest_incoming_date": str(crm.get("nearest_incoming_date") or ""),
            "future_stock_days": future_stock_days,
            "margin_before": margin_before,
            "margin_after": margin_after,
            "margin_available": card_key in margins,
            "margin_pre_pct": pct(margin_before, base["revenue"]) or Decimal("0"),
            "margin_post_pct": pct(margin_after, base["revenue"]) or Decimal("0"),
            "price_before_spp": dec(price.get("price_before_spp")),
            "price_with_spp": dec(price.get("price_with_spp")),
            "spp_percent": dec(price.get("spp_percent")),
            "previous_price_before_spp": dec(price.get("previous_price_before_spp")),
            "price_available": card_key in prices,
            "last_price_increase_date": last_increase_text,
            "recent_price_increase": bool(last_increase and last_increase >= recent_boundary),
            "rating": dec(review.get("rating")),
            "reviews": int(review.get("reviews") or 0),
            "review_available": card_key in reviews,
            "positions": positions.get(sku, {}),
            "position_source_date": position_source_date,
            "positions_fresh": positions_fresh,
            "mechanics": mechanics.get((account_id, sku), []),
            "fbo_supply_checked": True,
            "fbo_supply_confirmed": False,
            "fbo_supply_date": "",
            "fbo_supply_qty": Decimal("0"),
        }
        products.append(product)

    candidates = {
        row["sku"]
        for row in products
        if row["turnover_days"] is not None
        and row["turnover_days"] <= 5
        and row["yesterday_spend"] >= FBO_SPEND_ACTIVE_THRESHOLD
    }
    supply, supply_checked = load_fbo_supply_confirmation(candidates, current_date)
    for product in products:
        supply_row = supply.get(product["sku"], {})
        product["fbo_supply_checked"] = supply_checked
        product["fbo_supply_confirmed"] = bool(supply_row.get("confirmed"))
        product["fbo_supply_date"] = str(supply_row.get("nearest_date") or "")
        product["fbo_supply_qty"] = dec(supply_row.get("qty"))
        product.update(product_decision(product))

    products.sort(
        key=lambda row: (
            row["priority"]["rank"],
            -row["score"],
            -row["revenue"],
            int(row["sku"]) if row["sku"].isdigit() else row["sku"],
        )
    )
    return {
        "products": products,
        "position_source_date": position_source_date,
        "positions_fresh": positions_fresh,
        "fbo_supply_checked": supply_checked,
    }


def enrich_niche_priorities(summaries, products):
    products_by_category = defaultdict(list)
    for product in products:
        products_by_category[product["category"]].append(product)

    result = []
    for source in summaries:
        summary = dict(source)
        rows = products_by_category.get(summary["category"], [])
        revenue = sum((row["revenue"] for row in rows), Decimal("0"))
        margin_rows = [row for row in rows if row["margin_available"]]
        margin_before = sum((row["margin_before"] for row in margin_rows), Decimal("0"))
        margin_after = sum((row["margin_after"] for row in margin_rows), Decimal("0"))
        margin_revenue = sum((row["revenue"] for row in margin_rows), Decimal("0"))
        active_fbo = sum((row["fbo_stock"] for row in rows), Decimal("0"))
        orders = sum((row["orders"] for row in rows), Decimal("0"))
        crm_seen = set()
        incoming_qty = Decimal("0")
        for row in rows:
            if row["crm_id"] and row["crm_id"] not in crm_seen:
                crm_seen.add(row["crm_id"])
                incoming_qty += row["incoming_qty"]
        daily_orders = orders / Decimal(max(1, source.get("covered_days") or 1))
        turnover_days = ratio_days(active_fbo, daily_orders)
        future_days = ratio_days(active_fbo + incoming_qty, daily_orders)
        margin_pre_pct = pct(margin_before, margin_revenue) or Decimal("0")
        margin_post_pct = pct(margin_after, margin_revenue) or Decimal("0")
        drr_over = Decimal("0")
        if summary.get("actual_drr") is not None:
            drr_over = summary["actual_drr"] - summary["planned_drr"] if summary.get("planned_drr") is not None else summary["actual_drr"]
        critical_revenue = sum((row["revenue"] for row in rows if row["priority"]["code"] == "P1"), Decimal("0"))
        critical_share = pct(critical_revenue, revenue) or Decimal("0")
        low_stock_active = sum(
            1
            for row in rows
            if row["turnover_days"] is not None
            and row["turnover_days"] <= 3
            and row["yesterday_spend"] >= FBO_SPEND_ACTIVE_THRESHOLD
        )
        score = Decimal("0")
        plan_pct_value = summary.get("revenue_completion")
        if plan_pct_value is not None:
            score += 25 if plan_pct_value < 50 else 20 if plan_pct_value < 70 else 10 if plan_pct_value < 90 else 0
        score += 25 if drr_over > 10 else 18 if drr_over > 5 else 8 if drr_over > 0 else 0
        score += 25 if margin_pre_pct < -20 else 12 if margin_pre_pct < 0 else 0
        score += 8 if margin_post_pct < 0 else 0
        score += 20 if future_days is not None and future_days > 180 else 15 if future_days is not None and future_days > 120 else 8 if future_days is not None and future_days > 75 else 0
        score += 15 if critical_share > 50 else 8 if critical_share > 25 else 0
        score += 10 if low_stock_active else 0
        score = min(int(score), 100)
        growth = (
            plan_pct_value is not None
            and plan_pct_value >= 120
            and summary.get("planned_drr") is not None
            and summary.get("actual_drr") is not None
            and summary["actual_drr"] <= summary["planned_drr"]
            and margin_post_pct > 0
            and turnover_days is not None
            and turnover_days > 14
        )
        drivers = []
        if plan_pct_value is not None and plan_pct_value < 90:
            drivers.append(f"план {plan_pct_value:.1f}%")
        if summary.get("planned_drr") is not None and summary.get("actual_drr") is not None and summary["actual_drr"] > summary["planned_drr"]:
            drivers.append(f"ДРР {summary['actual_drr']:.1f}% / {summary['planned_drr']:.1f}%")
        if margin_pre_pct < 0:
            drivers.append(f"маржа до РК {margin_pre_pct:.1f}%")
        margin_coverage = pct(margin_revenue, revenue) or Decimal("0")
        if margin_coverage < 95:
            drivers.append(f"маржа покрывает {margin_coverage:.1f}% выручки")
        if future_days is not None and future_days > 75:
            drivers.append(
                "сток с CRM >999 дн." if future_days >= 9999 else f"сток с CRM {future_days:.1f} дн."
            )
        if low_stock_active:
            drivers.append(f"{low_stock_active} SKU с активной РК и FBO ≤3 дн.")
        growth_products = sum(1 for row in rows if row["growth"])
        if not drivers and growth_products:
            drivers.append(f"{growth_products} SKU с потенциалом масштабирования")
        if not drivers:
            drivers.append("критичных отклонений нет")
        summary.update(
            {
                "products": rows,
                "margin_before": margin_before,
                "margin_after": margin_after,
                "margin_pre_pct": margin_pre_pct,
                "margin_post_pct": margin_post_pct,
                "margin_coverage_pct": margin_coverage,
                "incoming_qty": incoming_qty,
                "active_turnover_days": turnover_days,
                "future_stock_days": future_days,
                "recent_price_increases": sum(1 for row in rows if row["recent_price_increase"]),
                "low_stock_active": low_stock_active,
                "score": score,
                "priority": priority(score, growth),
                "conclusion": " · ".join(drivers),
            }
        )
        result.append(summary)
    return sorted(result, key=lambda row: (row["priority"]["rank"], -row["score"], -row["spend"], row["category"]))
