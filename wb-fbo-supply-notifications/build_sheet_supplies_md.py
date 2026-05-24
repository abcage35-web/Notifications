#!/usr/bin/env python3
import csv
import io
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from custom_wb_fbo_supplies import McpSql


ROOT = Path(__file__).resolve().parent
REPORT_TZ = ZoneInfo(os.getenv("REPORT_TZ", "Asia/Tbilisi"))
START = datetime.now(REPORT_TZ).date()
STRICT_SOURCE_LOADING = os.getenv("STRICT_SOURCE_LOADING", "1") != "0"
REPORT_RUN_LABEL = os.getenv("REPORT_RUN_LABEL", "08:00 по МСК")
MARKETER_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4"
    "/gviz/tq?tqx=out:csv&gid=1574673852&range=D1:H430"
)
MANAGER_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1FWuNKO08UeuxCX4DI_S0gMmqLImCQXMVLPSMQ_tXWRI"
    "/gviz/tq?tqx=out:csv&gid=586703293&range=C1:F3492"
)
WB_CARD_DETAIL_URL = "https://card.wb.ru/cards/v4/detail"

MARKETER_BY_ARTICLE = {
    # Source: Google Sheets "ОП > ОВР переводчик", tab "ОВР (настройка)", D:H.
    "139710220": "@a.beaver",
    "160798202": "@a.manokhin",
    "224652683": "@a.beaver",
    "228705953": "@a.manokhin",
    "240176958": "@a.manokhin",
    "240176959": "@a.manokhin",
    "240176960": "@a.manokhin",
    "253488182": "@a.nekrasov",
    "261023141": "@a.nekrasov",
    "262513832": "@a.manokhin",
    "262513833": "@a.manokhin",
    "263077943": "@a.manokhin",
    "263077944": "@a.manokhin",
    "263077945": "@a.manokhin",
    "263077946": "@a.manokhin",
    "263077947": "@a.manokhin",
    "263077948": "@a.manokhin",
    "263077949": "@a.manokhin",
    "365479721": "@a.beaver",
    "366314867": "@a.manokhin",
    "390628787": "@a.nekrasov",
    "697925600": "@a.beaver",
    "699854628": "@a.manokhin",
    "699854629": "@a.manokhin",
    "837402498": "@a.nekrasov",
    "837573827": "@a.beaver",
    "837579658": "@a.beaver",
}


def load_marketer_by_article():
    marketers = dict(MARKETER_BY_ARTICLE)
    request = Request(MARKETER_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8-sig")
    except Exception as exc:
        if STRICT_SOURCE_LOADING:
            raise RuntimeError("Не удалось загрузить таблицу маркетологов") from exc
        return marketers
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 5:
            continue
        article = str(row[0]).strip()
        tag = str(row[4]).strip()
        if article.isdigit() and tag.startswith("@"):
            marketers[article] = tag
    return marketers


def load_manager_by_article():
    manager_tags = {
        "оля": "@o.eshmakova",
        "никита": "@n.aisin",
        "максим": "@m.gorokhov",
    }
    request = Request(MANAGER_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8-sig")
    except Exception as exc:
        if STRICT_SOURCE_LOADING:
            raise RuntimeError("Не удалось загрузить таблицу менеджеров") from exc
        return {}
    managers = {}
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 4:
            continue
        article = str(row[0]).strip()
        manager_name = str(row[3]).strip().lower()
        manager = manager_tags.get(manager_name)
        if article.isdigit() and manager:
            managers[article] = manager
    return managers


def load_wb_card_metrics_by_article(articles):
    result = {}
    errors = []
    article_list = sorted({str(article) for article in articles if str(article).isdigit()})
    for offset in range(0, len(article_list), 80):
        chunk = article_list[offset : offset + 80]
        query = urlencode(
            {
                "appType": 1,
                "curr": "rub",
                "dest": -1257786,
                "spp": 30,
                "ab_testing": "false",
                "nm": ";".join(chunk),
            },
            safe=";",
        )
        request = Request(
            f"{WB_CARD_DETAIL_URL}?{query}",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            errors.append(f"{chunk[0]}...{chunk[-1]}: {exc}")
            continue
        for product in payload.get("products") or []:
            article = str(product.get("id") or "")
            try:
                points = int(float(product.get("feedbackPoints") or 0))
            except (TypeError, ValueError):
                points = 0
            try:
                nm_feedbacks = int(float(product.get("nmFeedbacks") or 0))
            except (TypeError, ValueError):
                nm_feedbacks = 0
            try:
                nm_review_rating = float(product.get("nmReviewRating") or 0)
            except (TypeError, ValueError):
                nm_review_rating = 0.0
            if article:
                result[article] = {
                    "feedback_points": points,
                    "nm_feedbacks": nm_feedbacks,
                    "nm_review_rating": nm_review_rating,
                }
    if errors and STRICT_SOURCE_LOADING:
        raise RuntimeError("Не удалось загрузить WB card metrics: " + "; ".join(errors))
    return result


def google_access_token():
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        return None
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account

    info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def load_google_values(spreadsheet_id, range_name):
    token = google_access_token()
    if not token:
        return None
    encoded_range = quote(range_name, safe="")
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        f"/values/{encoded_range}?majorDimension=ROWS&valueRenderOption=UNFORMATTED_VALUE"
    )
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("values") or []


def load_csv_values(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=60) as response:
        raw = response.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(raw)))


def load_supply_sheet_rows():
    rows = []
    errors = []
    for source in SUPPLY_SHEET_SOURCES:
        try:
            values = load_google_values(SUPPLY_SPREADSHEET_ID, source["range"])
            if values is None:
                values = load_csv_values(source["csv_url"])
        except Exception as exc:
            errors.append(f"{source['name']}: {exc}")
            continue
        rows.extend(values)
    if errors:
        raise RuntimeError("Не удалось загрузить Google Sheets поставок FBO: " + "; ".join(errors))
    return rows

SUPPLY_SPREADSHEET_ID = os.getenv(
    "FBO_SUPPLY_SPREADSHEET_ID",
    "1kLX5hGPK3g8HRno39POiHheg9UIFXNkKQGKcpAXX1KM",
)
SUPPLY_SHEET_SOURCES = [
    {
        "name": "ВБ. Новый",
        "range": "'ВБ. Новый'!C:O",
        "csv_url": "https://docs.google.com/spreadsheets/d/1kLX5hGPK3g8HRno39POiHheg9UIFXNkKQGKcpAXX1KM/gviz/tq?tqx=out:csv&gid=876111045&range=C:O",
    },
    {
        "name": "ВБ. Регионы",
        "range": "'ВБ. Регионы'!C:O",
        "csv_url": "https://docs.google.com/spreadsheets/d/1kLX5hGPK3g8HRno39POiHheg9UIFXNkKQGKcpAXX1KM/gviz/tq?tqx=out:csv&gid=1978923499&range=C:O",
    },
]
# Indexes inside Google Sheets range C:O: 0=date, 9=product text, 10=vendor article, 11=barcode, 12=qty.

def sheet_serial_to_date(serial):
    return date(1899, 12, 30) + timedelta(days=int(serial))


def parse_sheet_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return sheet_serial_to_date(value)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        return sheet_serial_to_date(float(text.replace(",", ".")))
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_int(value):
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_wb_article(product_text, barcode):
    matches = re.findall(r"/\s*(\d{7,})\s*/\s*\d{10,}", product_text or "")
    if matches:
        return matches[-1]
    return None


def clean_name(product_text):
    parts = [p.strip() for p in (product_text or "").split("/")]
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit():
        return parts[0]
    return (product_text or "").strip().rstrip(",")


def load_rk_by_article(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku,
               COUNT(DISTINCT campaign_id) AS rk_count,
               SUM(CASE WHEN state = 9 THEN 1 ELSE 0 END) AS active_count,
               SUM(CASE WHEN state = 11 THEN 1 ELSE 0 END) AS paused_count,
               GROUP_CONCAT(DISTINCT campaign_id ORDER BY campaign_id SEPARATOR ', ') AS campaign_ids
        FROM (
            SELECT card.sku, campaign.campaign_id, campaign.state
            FROM mp.wb_core__card card
            JOIN mp.wb_core__campaign_card campaign_card
              ON campaign_card.card_id = card.card_id
             AND campaign_card.account_id = card.account_id
             AND campaign_card.date_at = (SELECT MAX(date_at) FROM mp.wb_core__campaign_card)
            JOIN mp.wb_core__campaign campaign
              ON campaign.campaign_id = campaign_card.campaign_id
             AND campaign.account_id = campaign_card.account_id
            WHERE CAST(card.sku AS UNSIGNED) IN ({article_num_sql})
              AND campaign.state IN (4, 9, 11)

            UNION

            SELECT card.sku, campaign.campaign_id, campaign.state
            FROM mp.wb_core__card card
            JOIN mp.wb_core__campaign campaign
              ON campaign.account_id = card.account_id
             AND FIND_IN_SET(CAST(card.sku AS CHAR), REPLACE(CAST(campaign.sku_list AS CHAR), ' ', '')) > 0
            WHERE CAST(card.sku AS UNSIGNED) IN ({article_num_sql})
              AND campaign.state IN (4, 9, 11)
        ) current_campaigns
        GROUP BY sku;
        """
    )
    result = {}
    for row in rows:
        sku = str(row.get("sku"))
        count = int(row.get("rk_count") or 0)
        result[sku] = {
            "rk_created": count > 0,
            "rk_count": count,
            "rk_active_count": int(row.get("active_count") or 0),
            "rk_paused_count": int(row.get("paused_count") or 0),
            "rk_campaign_ids": row.get("campaign_ids") or "",
        }
    return result


def load_ad_spend_by_article(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    spend_from = START - timedelta(days=2)
    spend_to = START
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku, ROUND(SUM(consumptions), 0) AS spend
        FROM mp.wb_core__campaign_stat_daily_sku
        WHERE CAST(sku AS UNSIGNED) IN ({article_num_sql})
          AND date_at BETWEEN '{spend_from.isoformat()}' AND '{spend_to.isoformat()}'
        GROUP BY sku;
        """
    )
    return {str(row.get("sku")): int(float(row.get("spend") or 0)) for row in rows}


def load_orders_7d_by_article(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    rows = db.query(
        f"""
        SELECT CAST(sku AS CHAR) AS sku,
               COUNT(DISTINCT COALESCE(NULLIF(srid, ''), order_number)) AS orders_7d
        FROM mp.wb_core__order
        WHERE CAST(sku AS UNSIGNED) IN ({article_num_sql})
          AND DATE(order_date) BETWEEN DATE('{START.isoformat()}') - INTERVAL 6 DAY
                                  AND DATE('{START.isoformat()}')
          AND COALESCE(is_cancel, 0) = 0
        GROUP BY sku;
        """
    )
    return {str(row.get("sku")): int(row.get("orders_7d") or 0) for row in rows}


def load_price_by_article(db, articles):
    article_num_sql = ",".join(sorted(str(a) for a in articles if str(a).isdigit()))
    if not article_num_sql:
        return {}
    result = {}
    realtime_rows = db.query(
        f"""
        SELECT CAST(card.sku AS CHAR) AS sku,
               ROUND(MAX(price_data.price), 0) AS price_before_spp,
               ROUND(MAX(NULLIF(price_data.price_mp, 0)), 0) AS price_with_spp,
               ROUND(MAX(NULLIF(price_data.discount_mp, -1)), 0) AS spp_percent
        FROM mp.wb_core__card card
        JOIN mp.mp_core__realtime_prices price_data
          ON price_data.card_id = card.card_id
         AND price_data.account_id = card.account_id
        WHERE price_data.date = (SELECT MAX(date) FROM mp.mp_core__realtime_prices)
          AND CAST(card.sku AS UNSIGNED) IN ({article_num_sql})
        GROUP BY card.sku;
        """
    )
    for row in realtime_rows:
        sku = str(row.get("sku"))
        result[sku] = {
            "price_before_spp": float(row.get("price_before_spp") or 0),
            "price_with_spp": float(row.get("price_with_spp") or 0),
            "spp_percent": float(row.get("spp_percent") or 0),
        }

    price_rows = db.query(
        f"""
        SELECT CAST(card.sku AS CHAR) AS sku,
               ROUND(price_data.price * (100 - price_data.discount_percent) / 100, 0) AS price_before_spp,
               ROUND(price_data.marketing_price, 0) AS price_with_spp,
               ROUND(NULLIF(price_data.spp_percent, -1), 0) AS spp_percent
        FROM mp.wb_core__card card
        JOIN mp.wb_core__price price_data
          ON price_data.card_id = card.card_id
         AND price_data.account_id = card.account_id
         AND price_data.date_at = (
             SELECT MAX(latest_price.date_at)
             FROM mp.wb_core__price latest_price
             WHERE latest_price.card_id = card.card_id
               AND latest_price.account_id = card.account_id
         )
        WHERE CAST(card.sku AS UNSIGNED) IN ({article_num_sql});
        """
    )
    for row in price_rows:
        sku = str(row.get("sku"))
        current = result.setdefault(sku, {"price_before_spp": 0, "price_with_spp": 0, "spp_percent": 0})
        if not current.get("price_before_spp"):
            current["price_before_spp"] = float(row.get("price_before_spp") or 0)
        if not current.get("price_with_spp"):
            current["price_with_spp"] = float(row.get("price_with_spp") or 0)
        if not current.get("spp_percent"):
            current["spp_percent"] = float(row.get("spp_percent") or 0)
    return result


def main():
    source_rows = []
    barcodes = set()
    parsed_articles = set()
    supply_sheet_rows = load_supply_sheet_rows()
    for row in supply_sheet_rows:
        if len(row) < 13:
            continue
        row_date = parse_sheet_date(row[0])
        if not row_date or row_date <= START:
            continue
        product = str(row[9]).strip()
        qty = to_int(row[12])
        if not product or not qty:
            continue
        # Skip warehouse marker rows that have no barcode/qty.
        barcode = str(row[11]).strip() if len(row) > 11 and row[11] else ""
        vendor = str(row[10]).strip() if len(row) > 10 and row[10] else ""
        article = parse_wb_article(product, barcode)
        if barcode:
            barcodes.add(barcode)
        if article:
            parsed_articles.add(article)
        source_rows.append(
            {
                "date": row_date,
                "product_raw": product,
                "name_from_sheet": clean_name(product),
                "vendor": vendor,
                "barcode": barcode,
                "qty": qty,
                "article_from_text": article,
                "source": "google_sheet",
            }
        )

    db = McpSql()
    try:
        accepted_from = START - timedelta(days=1)
        accepted_to = START + timedelta(days=1)
        accepted_rows = db.query(
            f"""
            SELECT CAST(supply_content.sku AS CHAR) AS sku,
                   MAX(supply_content.barcode) AS barcode,
                   SUM(COALESCE(supply_content.count_fact, 0)) AS accepted_qty,
                   GROUP_CONCAT(DISTINCT DATE(supply.supplied_at) ORDER BY DATE(supply.supplied_at)) AS accepted_dates
            FROM mp.wb_core__supply supply
            JOIN mp.wb_core__supply_contents supply_content
              ON supply_content.supply_id = supply.supply_id
             AND supply_content.account_id = supply.account_id
            WHERE supply.supplied_at >= '{accepted_from.isoformat()}'
              AND supply.supplied_at < '{accepted_to.isoformat()}'
            GROUP BY supply_content.sku
            HAVING accepted_qty > 0;
            """
        )
        for row in accepted_rows:
            article = str(row.get("sku") or "").strip()
            if not article:
                continue
            barcode = str(row.get("barcode") or "").strip()
            qty = int(float(row.get("accepted_qty") or 0))
            parsed_articles.add(article)
            if barcode:
                barcodes.add(barcode)
            source_rows.append(
                {
                    "date": START,
                    "product_raw": "",
                    "name_from_sheet": "-",
                    "vendor": "",
                    "barcode": barcode,
                    "qty": qty,
                    "article_from_text": article,
                    "source": "wb_api_accepted",
                    "accepted_dates": row.get("accepted_dates") or "",
                }
            )

        barcode_sql = ",".join("'" + b.replace("'", "''") + "'" for b in sorted(barcodes))
        article_num_sql = ",".join(a for a in sorted(parsed_articles) if a.isdigit())
        card_where = []
        if barcode_sql:
            card_where.append(f"barcode IN ({barcode_sql})")
        if article_num_sql:
            card_where.append(f"CAST(sku AS UNSIGNED) IN ({article_num_sql})")
        card_where_sql = " OR ".join(card_where) or "1 = 0"
        card_rows = db.query(
            f"""
            SELECT sku, barcode, short_name, object AS category
            FROM mp.wb_core__card
            WHERE {card_where_sql};
            """
        )
        stock_skus = {str(r.get("sku")) for r in card_rows if r.get("sku") is not None}
        stock_skus.update(parsed_articles)
        stock_num_sql = ",".join(sorted(s for s in stock_skus if s.isdigit()))
        if stock_num_sql:
            stock_rows = db.query(
                f"""
                SELECT CAST(sku AS CHAR) AS sku, SUM(fbo_real) AS fbo_current
                FROM mp.mp_core__realtime_stocks_data
                WHERE date = (SELECT MAX(date) FROM mp.mp_core__realtime_stocks_data)
                  AND CAST(sku AS UNSIGNED) IN ({stock_num_sql})
                GROUP BY sku;
                """
            )
            rk_by_article = load_rk_by_article(db, stock_skus)
            ad_spend_by_article = load_ad_spend_by_article(db, stock_skus)
            orders_7d_by_article = load_orders_7d_by_article(db, stock_skus)
            price_by_article = load_price_by_article(db, stock_skus)
        else:
            stock_rows = []
            rk_by_article = {}
            ad_spend_by_article = {}
            orders_7d_by_article = {}
            price_by_article = {}
    finally:
        db.close()

    by_barcode = {str(r.get("barcode")): r for r in card_rows if r.get("barcode")}
    by_sku = {str(r.get("sku")): r for r in card_rows if r.get("sku") is not None}
    stocks = {str(r.get("sku")): int(float(r.get("fbo_current") or 0)) for r in stock_rows}
    marketer_by_article = load_marketer_by_article()
    manager_by_article = load_manager_by_article()
    wb_card_metrics_by_article = load_wb_card_metrics_by_article(stock_skus)

    grouped = defaultdict(
        lambda: {
            "qty": 0,
            "name": "-",
            "category": "-",
            "manager": "-",
            "fbo": 0,
            "marketer": "-",
            "rk_created": False,
            "rk_count": 0,
            "rk_campaign_ids": "",
            "ad_spend_3d": 0,
            "feedback_points": 0,
            "nm_feedbacks": 0,
            "nm_review_rating": 0.0,
            "orders_7d": 0,
            "price_before_spp": 0,
            "price_with_spp": 0,
            "spp_percent": 0,
        }
    )
    unresolved = []
    for row in source_rows:
        card = None
        if row["article_from_text"]:
            card = by_sku.get(row["article_from_text"])
        if not card and row["barcode"]:
            card = by_barcode.get(row["barcode"])
        article = row["article_from_text"] or (str(card["sku"]) if card and card.get("sku") else "")
        if not article:
            unresolved.append(row)
            article = f"barcode:{row['barcode'] or row['vendor']}"
        name = (card or {}).get("short_name") or row["name_from_sheet"]
        category = (card or {}).get("category") or "-"
        key = (row["date"], article)
        grouped[key]["qty"] += row["qty"]
        grouped[key]["name"] = name
        grouped[key]["category"] = category
        grouped[key]["manager"] = manager_by_article.get(article, "-")
        grouped[key]["fbo"] = stocks.get(article, 0)
        grouped[key]["marketer"] = marketer_by_article.get(article, "-")
        rk_info = rk_by_article.get(article, {})
        grouped[key]["rk_created"] = bool(rk_info.get("rk_created"))
        grouped[key]["rk_count"] = int(rk_info.get("rk_count") or 0)
        grouped[key]["rk_campaign_ids"] = rk_info.get("rk_campaign_ids", "")
        grouped[key]["ad_spend_3d"] = ad_spend_by_article.get(article, 0)
        wb_metrics = wb_card_metrics_by_article.get(article, {})
        grouped[key]["feedback_points"] = int(wb_metrics.get("feedback_points") or 0)
        grouped[key]["nm_feedbacks"] = int(wb_metrics.get("nm_feedbacks") or 0)
        grouped[key]["nm_review_rating"] = float(wb_metrics.get("nm_review_rating") or 0)
        grouped[key]["orders_7d"] = orders_7d_by_article.get(article, 0)
        price_info = price_by_article.get(article, {})
        grouped[key]["price_before_spp"] = float(price_info.get("price_before_spp") or 0)
        grouped[key]["price_with_spp"] = float(price_info.get("price_with_spp") or 0)
        grouped[key]["spp_percent"] = float(price_info.get("spp_percent") or 0)

    def label(d):
        if d == START:
            return "Сегодня"
        if d == START + timedelta(days=1):
            return "Завтра"
        return "Послезавтра"

    def md_cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def rk_created_label(info):
        return "да" if info.get("rk_created") else "нет"

    def rub(value):
        return f"{int(value or 0):,}".replace(",", " ") + " ₽"

    def underline_text(text):
        return text

    def bzo_label(info):
        points = int(info.get("feedback_points") or 0)
        if points > 0:
            return f"да ({rub(points)})"
        return "нет"

    def needs_bzo_action(info):
        return (
            int(info.get("feedback_points") or 0) <= 0
            and int(info.get("nm_feedbacks") or 0) < 10
            and int(info.get("orders_7d") or 0) < 10
        )

    def reviews_label(info):
        return str(int(info.get("nm_feedbacks") or 0))

    def rating_label(info):
        rating = float(info.get("nm_review_rating") or 0)
        return f"{rating:.1f}".replace(".", ",") if rating else "0"

    def bzo_reviews_rating_label(info):
        return f"{bzo_label(info)} / {reviews_label(info)} ({rating_label(info)} ★)"

    def reviews_rating_label(info):
        return f"{reviews_label(info)} ({rating_label(info)} ★)"

    def article_md(article):
        return f"`{md_cell(article)}`"

    def rk_message_label(info):
        label = "да" if info.get("rk_created") else f"**{underline_text('СОЗДАТЬ РК')}**"
        return f"{label} (траты 3д: {rub(info.get('ad_spend_3d'))})"

    def message_marketer_label(info):
        return "`не указан маркетолог`" if info.get("marketer") == "-" else info["marketer"]

    def message_manager_label(info):
        return "`не указан менеджер`" if info.get("manager") == "-" else info["manager"]

    def bzo_message_recipient_label(info):
        return f"{message_manager_label(info)} / @e.khanzhova"

    def price_label(value):
        amount = int(round(float(value or 0)))
        return rub(amount) if amount > 0 else "-"

    def price_spp_label(info):
        price_before_spp = float(info.get("price_before_spp") or 0)
        price_with_spp = float(info.get("price_with_spp") or 0)
        spp_percent = float(info.get("spp_percent") or 0)
        if not spp_percent and price_before_spp > 0 and price_with_spp > 0:
            spp_percent = round((1 - price_with_spp / price_before_spp) * 100)
        spp_label = f" ({int(round(spp_percent))}%)" if price_with_spp > 0 and spp_percent > 0 else ""
        return f"{price_label(price_before_spp)} / {price_label(price_with_spp)}{spp_label}"

    def needs_price_action(offset, info):
        return float(info.get("price_before_spp") or 0) > 80000

    def action_label(info, check_price=False, include_rk_activity=True):
        actions = []
        if check_price:
            actions.append("Цена: проверить цену")
        if needs_bzo_action(info):
            actions.append("БЗО: включить БЗО")
        if not info.get("rk_created"):
            actions.append("РК: включить РК")
        elif include_rk_activity and float(info.get("ad_spend_3d") or 0) < 3000:
            actions.append("РК: проверить активность РК")
        return "<br>".join(actions) if actions else "-"

    def message_recommendations(info, check_price=False, include_rk_activity=True):
        recommendations = []
        if check_price:
            recommendations.append(
                f"ЦЕНА: **ПРОВЕРИТЬ ЦЕНУ** (*цена / спп: {price_spp_label(info)}*) / {message_manager_label(info)}"
            )
        if needs_bzo_action(info):
            recommendations.append(
                f"БЗО: **ВКЛЮЧИТЬ БЗО** (*отзывы: {reviews_label(info)} ({rating_label(info)} ★)*) / {bzo_message_recipient_label(info)}"
            )
        if not info.get("rk_created"):
            recommendations.append(
                f"РК: **{underline_text('СОЗДАТЬ РК')}** (*траты 3д: {rub(info.get('ad_spend_3d'))}*) / {message_marketer_label(info)}"
            )
        elif include_rk_activity and float(info.get("ad_spend_3d") or 0) < 3000:
            recommendations.append(
                f"РК: **ПРОВЕРИТЬ АКТИВНОСТЬ РК** (*траты 3д: {rub(info.get('ad_spend_3d'))}*) / {message_marketer_label(info)}"
            )
        return recommendations

    lines = ["# Поставки FBO WB на ближайшие 3 дня", ""]
    lines.append(
        f"_Источник: `сегодня` - принятые товары WB за {(START - timedelta(days=1)).strftime('%d.%m.%Y')}"
        f" и {START.strftime('%d.%m.%Y')} по `count_fact`, одним списком с суммированием по артикулу; "
        "будущие дни - Google Sheets `Поставки ФБО МП`, вкладки `ВБ. Новый` и `ВБ. Регионы`, колонки C, L:M, O; "
        "менеджер - Google Sheets `Репрайсер MVP`, лист `РАБОЧИЙ ЛИСТ`, колонки C и F._"
    )
    lines.append("")
    summary_insert_index = len(lines)
    for offset in range(3):
        d = START + timedelta(days=offset)
        lines.append(f"{label(d)} ({d.strftime('%d.%m.%Y')}):")
        lines.append("")
        day_items = [
            (article, info)
            for (item_date, article), info in grouped.items()
            if item_date == d
        ]
        if not day_items:
            lines.append("_Нет строк в источнике._")
        else:
            lines.append("| Поставка | Артикул ВБ | Название товара | Категория | Действие | Наличие кампании РК | Траты (3д) | Отзывы и рейтинг | БЗО | Заказы (7д) | Цена / СПП | Менеджер | Маркетолог |")
            lines.append("|---|---:|---|---|---|---|---:|---|---|---:|---|---|---|")
            for article, info in sorted(day_items, key=lambda x: (-x[1]["qty"], str(x[0]))):
                if d == START:
                    supply = f"`{info['fbo']}` (`+{info['qty']}`)"
                else:
                    supply = f"`{info['fbo']}` -> `+{info['qty']}`"
                lines.append(
                    f"| {supply} | {article_md(article)} | {md_cell(info['name'])} | {md_cell(info['category'])} | {action_label(info, needs_price_action(offset, info), offset == 0)} | {rk_created_label(info)} | {rub(info.get('ad_spend_3d'))} | {reviews_rating_label(info)} | {bzo_label(info)} | {int(info.get('orders_7d') or 0)} | {price_spp_label(info)} | {md_cell(info['manager'])} | {md_cell(info['marketer'])} |"
                )
        lines.append("")

    action_rules = [0, 1]
    message_item_separator = "\\-----------------------------------------------"

    def pachca_message_text(lines_to_render):
        # Pachca treats regular Markdown newlines as soft breaks in some messages.
        # Two trailing spaces force a hard line break while keeping readable source files.
        return "\n".join(f"{line}  " if line else "" for line in lines_to_render).rstrip()

    action_lines = []
    action_items = []
    for offset in action_rules:
        d = START + timedelta(days=offset)
        items = [
            (article, info)
            for (item_date, article), info in grouped.items()
            if item_date == d
            and info["qty"] > 0
            and (
                (offset == 0 and (info["fbo"] - info["qty"]) <= 100)
                or (offset != 0 and info["fbo"] < 100)
            )
        ]
        if not items:
            continue
        if action_lines:
            action_lines.append("")
        title = "ВЧЕРА и СЕГОДНЯ" if offset == 0 else label(d).upper()
        action_lines.append(f"**{title}:**")
        sorted_items = sorted(items, key=lambda x: ((x[1]["fbo"] - x[1]["qty"]) if offset == 0 else x[1]["fbo"], -x[1]["qty"], str(x[0])))
        for index, (article, info) in enumerate(sorted_items):
            supply = (
                f"`{info['fbo']}` (`+{info['qty']}`)"
                if offset == 0
                else f"`{info['fbo']}` -> `+{info['qty']}`"
            )
            action_lines.append(
                f"{supply} / `{article}` / {info['name']}"
            )
            for recommendation in message_recommendations(info, needs_price_action(offset, info), offset == 0):
                action_lines.append(f"↳ {recommendation}")
            action_items.append(
                {
                    "block": title,
                    "offset": offset,
                    "article": article,
                    "supply": supply,
                    **info,
                }
            )
            if index < len(sorted_items) - 1:
                action_lines.append(message_item_separator)
    if not action_lines:
        action_lines.append("Нет товаров под условия: поставка запланирована и остаток FBO < 100.")
    action_lines = [f"**ПОСТАВКИ FBO WB (отчет {REPORT_RUN_LABEL})**", ""] + action_lines

    summary_lines = [
        "# ТОВАРЫ ИЗ ТЕКСТОВОЙ СВОДКИ",
        "",
        "_Логика: вчера/сегодня - принятая поставка WB и FBO до прихода <= 100; завтра - плановая поставка и текущий FBO < 100. Поставки суммируются по артикулу._",
        "",
    ]
    if action_items:
        for block_title in ["ВЧЕРА и СЕГОДНЯ", "ЗАВТРА"]:
            block_items = [item for item in action_items if item["block"] == block_title]
            if not block_items:
                continue
            summary_lines.append(f"### {block_title}")
            summary_lines.append("")
            summary_lines.append("| Поставка | Артикул ВБ | Название товара | Категория | Действие | Наличие кампании РК | Траты (3д) | Отзывы и рейтинг | БЗО | Заказы (7д) | Цена / СПП | Менеджер | Маркетолог |")
            summary_lines.append("|---|---:|---|---|---|---|---:|---|---|---:|---|---|---|")
            for item in block_items:
                item_offset = int(item.get("offset") or 0)
                summary_lines.append(
                    f"| {item['supply']} | {article_md(item['article'])} | {md_cell(item['name'])} | {md_cell(item['category'])} | {action_label(item, needs_price_action(item_offset, item), item_offset == 0)} | {rk_created_label(item)} | {rub(item.get('ad_spend_3d'))} | {reviews_rating_label(item)} | {bzo_label(item)} | {int(item.get('orders_7d') or 0)} | {price_spp_label(item)} | {md_cell(item['manager'])} | {md_cell(item['marketer'])} |"
                )
            summary_lines.append("")
    else:
        summary_lines.append("_Нет товаров, которые попали в текстовую сводку._")
        summary_lines.append("")
    missing_marketer_by_article = {}
    for item in action_items:
        if item["marketer"] == "-" and item["article"] not in missing_marketer_by_article:
            missing_marketer_by_article[item["article"]] = item

    thread_lines = []
    if missing_marketer_by_article:
        thread_lines.append(
            "**@a.nekrasov, добавь, пожалуйста, ответственных маркетологов за артикулами:**"
        )
        for article, info in sorted(missing_marketer_by_article.items(), key=lambda x: str(x[0])):
            thread_lines.append(f"- `{article}` / {info['name']}")

    summary_lines.append("# ЗАПРОС НА ДОБАВЛЕНИЕ ОТВЕТСТВЕННЫХ МАРКЕТОЛОГОВ")
    summary_lines.append("")
    if missing_marketer_by_article:
        summary_lines.extend(thread_lines)
        summary_lines.append("")
        summary_lines.append("Список артикулов для копирования:")
        summary_lines.append("")
        summary_lines.append("```text")
        for article in sorted(missing_marketer_by_article, key=str):
            summary_lines.append(str(article))
        summary_lines.append("```")
    else:
        summary_lines.append("_Все товары из текстовой сводки имеют указанного маркетолога._")
    summary_lines.extend([
        "",
        "",
        "# ПОЛНЫЙ СПИСОК ПОСТАВОК",
        "",
    ])
    lines[summary_insert_index:summary_insert_index] = summary_lines

    report_date = START.isoformat()
    out = ROOT / f"pachca_fbo_supplies_sheet_{report_date}.md"
    out_message = ROOT / f"pachca_fbo_supplies_sheet_{report_date}_message.md"
    out_thread_message = ROOT / f"pachca_fbo_supplies_sheet_{report_date}_thread.md"
    out_json = ROOT / f"pachca_fbo_supplies_sheet_{report_date}.json"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    rendered_message = pachca_message_text(action_lines)
    out_message.write_text(rendered_message + "\n", encoding="utf-8")
    out_thread_message.write_text("\n".join(thread_lines).rstrip() + "\n", encoding="utf-8")
    out_json.write_text(
        json.dumps(
            {
                "items": [
                    {"date": str(d), "article": a, **info}
                    for (d, a), info in grouped.items()
                ],
                "unresolved": unresolved,
                "message": rendered_message,
                "thread_message": "\n".join(thread_lines).rstrip(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"md": str(out), "message": str(out_message), "thread_message": str(out_thread_message), "items": len(grouped), "unresolved": len(unresolved)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
