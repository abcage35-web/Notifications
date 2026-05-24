#!/usr/bin/env python3
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FBO_ROOT = ROOT.parent / "wb-fbo-supply-notifications"
sys.path.insert(0, str(FBO_ROOT))

import build_sheet_supplies_md as fbo  # noqa: E402
from custom_wb_fbo_supplies import McpSql  # noqa: E402


START = datetime.now(fbo.REPORT_TZ).date()
REPORT_RUN_LABEL = os.getenv("REPORT_RUN_LABEL", "08:05 по МСК")
ACTION_MIN_FBO = int(os.getenv("ACTION_MIN_FBO", "50"))
PRICE_ACTION_THRESHOLD = int(os.getenv("PRICE_ACTION_THRESHOLD", "80000"))
RK_LOW_SPEND_THRESHOLD = int(os.getenv("RK_LOW_SPEND_THRESHOLD", "3000"))
DRR_DISABLE_THRESHOLD = float(os.getenv("DRR_DISABLE_THRESHOLD", "4"))
TURNOVER_DISABLE_DAYS = float(os.getenv("TURNOVER_DISABLE_DAYS", "5"))
SUPPLY_LOOKAHEAD_DAYS = int(os.getenv("SUPPLY_LOOKAHEAD_DAYS", "30"))
SUPPLY_DISABLE_MIN_DAYS = int(os.getenv("SUPPLY_DISABLE_MIN_DAYS", "5"))


def md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def article_md(article):
    return f"`{md_cell(article)}`"


def rub(value):
    return f"{int(round(float(value or 0))):,}".replace(",", " ") + " ₽"


def money_or_dash(value):
    amount = int(round(float(value or 0)))
    return rub(amount) if amount > 0 else "-"


def pct(value):
    return f"{float(value or 0):.1f}%".replace(".", ",")


def number(value):
    value = float(value or 0)
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}".replace(".", ",")


def price_spp_label(info):
    price_before_spp = float(info.get("price_before_spp") or 0)
    price_with_spp = float(info.get("price_with_spp") or 0)
    spp_percent = float(info.get("spp_percent") or 0)
    if not spp_percent and price_before_spp > 0 and price_with_spp > 0:
        spp_percent = round((1 - price_with_spp / price_before_spp) * 100)
    spp_label = f" ({int(round(spp_percent))}%)" if price_with_spp > 0 and spp_percent > 0 else ""
    return f"{money_or_dash(price_before_spp)} / {money_or_dash(price_with_spp)}{spp_label}"


def reviews_rating_label(info):
    rating = float(info.get("nm_review_rating") or 0)
    rating_label = f"{rating:.1f}".replace(".", ",") if rating else "0"
    return f"{int(info.get('nm_feedbacks') or 0)} ({rating_label} ★)"


def bzo_label(info):
    points = int(info.get("feedback_points") or 0)
    return f"да ({rub(points)})" if points > 0 else "нет"


def message_marketer_label(info):
    return "`не указан маркетолог`" if info.get("marketer") == "-" else info["marketer"]


def message_manager_label(info):
    return "`не указан менеджер`" if info.get("manager") == "-" else info["manager"]


def bzo_message_recipient_label(info):
    return f"{message_manager_label(info)} / @e.khanzhova"


def nearest_supply_label(info):
    supply = info.get("nearest_supply")
    if not supply:
        return "-"
    return f"{supply['date'].strftime('%d.%m.%Y')} (+{supply['qty']}, через {supply['days_until']}д)"


def pachca_message_text(lines):
    return "\n".join(f"{line}  " if line else "" for line in lines).rstrip()


def load_base_rows(db):
    rows = db.query(
        """
        WITH latest_stocks AS (
            SELECT CAST(sku AS CHAR) AS sku, SUM(fbo_real) AS fbo_current
            FROM mp.mp_core__realtime_stocks_data
            WHERE date = (SELECT MAX(date) FROM mp.mp_core__realtime_stocks_data)
            GROUP BY sku
        )
        SELECT CAST(card.sku AS CHAR) AS sku,
               MAX(card.short_name) AS name,
               MAX(card.object) AS category,
               COALESCE(MAX(latest_stocks.fbo_current), 0) AS fbo
        FROM mp.wb_core__card card
        JOIN latest_stocks
          ON latest_stocks.sku = CAST(card.sku AS CHAR)
        GROUP BY card.sku
        HAVING fbo > 0;
        """
    )
    return {
        str(row["sku"]): {
            "article": str(row["sku"]),
            "name": row.get("name") or "-",
            "category": row.get("category") or "-",
            "fbo": int(float(row.get("fbo") or 0)),
        }
        for row in rows
    }


def load_ad_spend_3d_excluding_today(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    spend_from = START - timedelta(days=3)
    spend_to = START - timedelta(days=1)
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku, ROUND(SUM(consumptions), 0) AS spend
        FROM mp.wb_core__campaign_stat_daily_sku
        WHERE CAST(sku AS UNSIGNED) IN ({article_num_sql})
          AND DATE(date_at) BETWEEN DATE('{spend_from.isoformat()}')
                                AND DATE('{spend_to.isoformat()}')
        GROUP BY sku;
        """
    )
    return {str(row.get("sku")): int(float(row.get("spend") or 0)) for row in rows}


def load_orders_3d_excluding_today(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    orders_from = START - timedelta(days=3)
    orders_to = START - timedelta(days=1)
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku,
               COUNT(*) AS orders_3d,
               ROUND(SUM(order_price), 0) AS revenue_3d
        FROM (
            SELECT sku,
                   COALESCE(NULLIF(srid, ''), order_number) AS order_key,
                   MAX(order_price) AS order_price
            FROM mp.wb_core__order
            WHERE CAST(sku AS UNSIGNED) IN ({article_num_sql})
              AND DATE(order_date) BETWEEN DATE('{orders_from.isoformat()}')
                                      AND DATE('{orders_to.isoformat()}')
              AND COALESCE(is_cancel, 0) = 0
            GROUP BY sku, order_key
        ) dedup_orders
        GROUP BY sku;
        """
    )
    result = {}
    for row in rows:
        sku = str(row.get("sku"))
        result[sku] = {
            "orders_3d_excl_today": int(row.get("orders_3d") or 0),
            "revenue_3d_excl_today": float(row.get("revenue_3d") or 0),
        }
    return result


def load_nearest_supplies():
    grouped = defaultdict(int)
    for row in fbo.load_supply_sheet_rows():
        if len(row) < 13:
            continue
        row_date = fbo.parse_sheet_date(row[0])
        if not row_date or row_date < START or row_date > START + timedelta(days=SUPPLY_LOOKAHEAD_DAYS):
            continue
        product = str(row[9]).strip() if len(row) > 9 and row[9] else ""
        barcode = str(row[11]).strip() if len(row) > 11 and row[11] else ""
        qty = fbo.to_int(row[12])
        article = fbo.parse_wb_article(product, barcode)
        if article and qty > 0:
            grouped[(article, row_date)] += qty

    nearest = {}
    for (article, supply_date), qty in grouped.items():
        days_until = (supply_date - START).days
        current = nearest.get(article)
        if not current or supply_date < current["date"]:
            nearest[article] = {"date": supply_date, "qty": qty, "days_until": days_until}
        elif current["date"] == supply_date:
            current["qty"] += qty
    return nearest


def enrich_items():
    db = McpSql()
    try:
        items = load_base_rows(db)
        articles = set(items)
        rk_by_article = fbo.load_rk_by_article(db, articles)
        ad_spend_by_article = fbo.load_ad_spend_by_article(db, articles)
        ad_spend_excl_by_article = load_ad_spend_3d_excluding_today(db, articles)
        orders_7d_by_article = fbo.load_orders_7d_by_article(db, articles)
        orders_3d_by_article = load_orders_3d_excluding_today(db, articles)
        price_by_article = fbo.load_price_by_article(db, articles)
    finally:
        db.close()

    marketer_by_article = fbo.load_marketer_by_article()
    manager_by_article = fbo.load_manager_by_article()
    wb_metrics_by_article = fbo.load_wb_card_metrics_by_article(articles)
    nearest_supplies = load_nearest_supplies()

    for article, info in items.items():
        rk_info = rk_by_article.get(article, {})
        info["rk_created"] = bool(rk_info.get("rk_created"))
        info["rk_count"] = int(rk_info.get("rk_count") or 0)
        info["rk_campaign_ids"] = rk_info.get("rk_campaign_ids", "")
        info["ad_spend_3d"] = ad_spend_by_article.get(article, 0)
        info["ad_spend_3d_excl_today"] = ad_spend_excl_by_article.get(article, 0)
        order_stats = orders_3d_by_article.get(article, {})
        info["orders_3d_excl_today"] = int(order_stats.get("orders_3d_excl_today") or 0)
        info["revenue_3d_excl_today"] = float(order_stats.get("revenue_3d_excl_today") or 0)
        info["orders_7d"] = orders_7d_by_article.get(article, 0)
        metrics = wb_metrics_by_article.get(article, {})
        info["feedback_points"] = int(metrics.get("feedback_points") or 0)
        info["nm_feedbacks"] = int(metrics.get("nm_feedbacks") or 0)
        info["nm_review_rating"] = float(metrics.get("nm_review_rating") or 0)
        price = price_by_article.get(article, {})
        info["price_before_spp"] = float(price.get("price_before_spp") or 0)
        info["price_with_spp"] = float(price.get("price_with_spp") or 0)
        info["spp_percent"] = float(price.get("spp_percent") or 0)
        info["manager"] = manager_by_article.get(article, "-")
        info["marketer"] = marketer_by_article.get(article, "-")
        info["nearest_supply"] = nearest_supplies.get(article)

        orders_3d = int(info["orders_3d_excl_today"])
        info["turnover_3d"] = None
        if orders_3d > 0:
            info["turnover_3d"] = info["fbo"] / (orders_3d / 3)
        revenue_3d = float(info["revenue_3d_excl_today"] or 0)
        info["drr_3d_excl_today"] = (
            float(info["ad_spend_3d_excl_today"] or 0) / revenue_3d * 100 if revenue_3d > 0 else 0
        )

    return items


def has_action_stock(info):
    return int(info.get("fbo") or 0) >= ACTION_MIN_FBO


def is_price_action(info):
    return has_action_stock(info) and float(info.get("price_before_spp") or 0) >= PRICE_ACTION_THRESHOLD


def is_bzo_action(info):
    return (
        has_action_stock(info)
        and int(info.get("feedback_points") or 0) <= 0
        and int(info.get("nm_feedbacks") or 0) <= 10
        and int(info.get("orders_7d") or 0) <= 10
    )


def is_create_rk_action(info):
    return has_action_stock(info) and not info.get("rk_created")


def is_check_rk_action(info):
    return (
        has_action_stock(info)
        and bool(info.get("rk_created"))
        and float(info.get("ad_spend_3d") or 0) < RK_LOW_SPEND_THRESHOLD
    )


def is_disable_rk_action(info):
    supply = info.get("nearest_supply")
    supply_is_far_or_missing = not supply or int(supply.get("days_until") or 0) >= SUPPLY_DISABLE_MIN_DAYS
    turnover = info.get("turnover_3d")
    return (
        bool(info.get("rk_created"))
        and turnover is not None
        and turnover < TURNOVER_DISABLE_DAYS
        and (
            float(info.get("ad_spend_3d_excl_today") or 0) > RK_LOW_SPEND_THRESHOLD
            or float(info.get("drr_3d_excl_today") or 0) > DRR_DISABLE_THRESHOLD
        )
        and supply_is_far_or_missing
    )


def message_item_line(action, info):
    base = f"• {info['article']} / FBO: {int(info.get('fbo') or 0)}"
    if action == "price":
        return f"{base} / цена / спп: {price_spp_label(info)} / {info['name']} {message_manager_label(info)}"
    if action == "bzo":
        return (
            f"{base} / отзывы: {reviews_rating_label(info)} / "
            f"{info['name']} {bzo_message_recipient_label(info)}"
        )
    if action == "create_rk":
        return f"{base} / траты 3д: {rub(info.get('ad_spend_3d'))} / {info['name']} {message_marketer_label(info)}"
    if action == "check_rk":
        return (
            f"{base} / траты 3д: {rub(info.get('ad_spend_3d'))} / "
            f"{info['name']} {message_marketer_label(info)}"
        )
    if action == "disable_rk":
        return (
            f"{base} / оборачиваемость 3д: {number(info.get('turnover_3d'))} д / "
            f"траты 3д: {rub(info.get('ad_spend_3d_excl_today'))} / "
            f"ДРР 3д: {pct(info.get('drr_3d_excl_today'))} / "
            f"ближайшая поставка: {nearest_supply_label(info)} / "
            f"{info['name']} {message_marketer_label(info)}"
        )
    return "-"


def md_action_label(action):
    labels = {
        "price": "Цена: проверить цену",
        "bzo": "БЗО: включить БЗО",
        "create_rk": "РК: создать РК",
        "check_rk": "РК: проверить активность РК",
        "disable_rk": "РК: выключить РК",
    }
    return labels[action]


def table_row(action, info):
    return (
        f"| {article_md(info['article'])} | {md_cell(info['name'])} | {md_cell(info['category'])} | "
        f"{int(info.get('fbo') or 0)} | {md_action_label(action)} | {price_spp_label(info)} | "
        f"{reviews_rating_label(info)} | {bzo_label(info)} | {int(info.get('orders_7d') or 0)} | "
        f"{'да' if info.get('rk_created') else 'нет'} | {rub(info.get('ad_spend_3d'))} | "
        f"{number(info.get('turnover_3d')) if info.get('turnover_3d') is not None else '-'} | "
        f"{rub(info.get('ad_spend_3d_excl_today'))} | {pct(info.get('drr_3d_excl_today'))} | "
        f"{nearest_supply_label(info)} | {md_cell(info.get('manager') or '-')} | {md_cell(info.get('marketer') or '-')} |"
    )


def segment_sort(action, items):
    if action == "price":
        return sorted(items, key=lambda x: (-float(x.get("price_before_spp") or 0), str(x["article"])))
    if action == "disable_rk":
        return sorted(items, key=lambda x: (float(x.get("turnover_3d") or 999999), -float(x.get("drr_3d_excl_today") or 0), str(x["article"])))
    return sorted(items, key=lambda x: (-int(x.get("fbo") or 0), str(x["article"])))


def build_segments(items):
    values = list(items.values())
    segments = [
        ("price", "НАСТРОИТЬ ЦЕНУ", [item for item in values if is_price_action(item)]),
        ("bzo", "ВКЛЮЧИТЬ БЗО", [item for item in values if is_bzo_action(item)]),
        ("create_rk", "СОЗДАТЬ РК", [item for item in values if is_create_rk_action(item)]),
        ("check_rk", "ПРОВЕРИТЬ АКТИВНОСТЬ РК", [item for item in values if is_check_rk_action(item)]),
        ("disable_rk", "ВЫКЛЮЧИТЬ РК", [item for item in values if is_disable_rk_action(item)]),
    ]
    return [(key, title, segment_sort(key, rows)) for key, title, rows in segments]


def build_outputs(items):
    segments = build_segments(items)
    message_lines = [f"**ДЕЙСТВИЯ WB (отчет {REPORT_RUN_LABEL})**", ""]
    md_lines = [
        "# Действия WB",
        "",
        f"_Отчет сформирован: {START.strftime('%d.%m.%Y')}. Тестовый проект: `/действия_уведомление`._",
        "",
        "## Условия",
        "",
        f"- Цена: FBO >= {ACTION_MIN_FBO}, цена до СПП >= {PRICE_ACTION_THRESHOLD} руб.",
        f"- БЗО: FBO >= {ACTION_MIN_FBO}, БЗО нет, отзывов <= 10, заказов 7д <= 10.",
        f"- Создать РК: FBO >= {ACTION_MIN_FBO}, нет неархивной РК.",
        f"- Проверить активность РК: FBO >= {ACTION_MIN_FBO}, РК есть, траты 3д < {RK_LOW_SPEND_THRESHOLD} руб.",
        "- Выключить РК: оборачиваемость 3 полных дней < 5д, траты 3д > 3 000 руб. или ДРР 3д > 4%, ближайшая поставка через 5+ дней или отсутствует.",
        "",
    ]

    total_action_rows = 0
    header = "| Артикул ВБ | Название товара | Категория | FBO | Действие | Цена / СПП | Отзывы и рейтинг | БЗО | Заказы (7д) | Наличие кампании РК | Траты (3д) | Оборачиваемость (3д) | Траты РК (3д без сегодня) | ДРР (3д без сегодня) | Ближайшая поставка FBO | Менеджер | Маркетолог |"
    divider = "|---:|---|---|---:|---|---|---|---|---:|---|---:|---:|---:|---:|---|---|---|"

    for key, title, rows in segments:
        md_lines.append(f"## {title}")
        md_lines.append("")
        if rows:
            message_lines.append(f"**{title}:**")
            md_lines.append(header)
            md_lines.append(divider)
            for item in rows:
                total_action_rows += 1
                message_lines.append(message_item_line(key, item))
                md_lines.append(table_row(key, item))
            message_lines.append("")
            md_lines.append("")
        else:
            md_lines.append("_Нет товаров под условия._")
            md_lines.append("")

    if total_action_rows == 0:
        message_lines.append("Нет товаров под условия действий.")

    report_date = START.isoformat()
    out_md = ROOT / f"pachca_wb_actions_{report_date}.md"
    out_message = ROOT / f"pachca_wb_actions_{report_date}_message.md"
    out_json = ROOT / f"pachca_wb_actions_{report_date}.json"
    rendered_message = pachca_message_text(message_lines)

    out_md.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    out_message.write_text(rendered_message + "\n", encoding="utf-8")
    out_json.write_text(
        json.dumps(
            {
                "items": list(items.values()),
                "segments": {key: len(rows) for key, _, rows in segments},
                "message": rendered_message,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return {
        "md": str(out_md),
        "message": str(out_message),
        "json": str(out_json),
        "items": total_action_rows,
        "segments": {key: len(rows) for key, _, rows in segments},
    }


def main():
    items = enrich_items()
    print(json.dumps(build_outputs(items), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
