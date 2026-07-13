#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
START = datetime.now(ZoneInfo(os.getenv("REPORT_TZ", "Asia/Tbilisi"))).date()
END = START + timedelta(days=2)
CHAT_ID = int(os.getenv("PACHCA_CHAT_ID", "39363429"))


def codex_analyzer_token() -> str:
    env_token = os.getenv("ABCAGE_ANALYZER_TOKEN")
    if env_token:
        return env_token
    text = (Path.home() / ".codex/config.toml").read_text(encoding="utf-8")
    match = re.search(r'ABCAGE_ANALYZER_TOKEN\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("ABCAGE_ANALYZER_TOKEN not found")
    return match.group(1)


class McpSql:
    def __init__(self):
        env = os.environ.copy()
        env["ABCAGE_ANALYZER_TOKEN"] = codex_analyzer_token()
        self.proc = subprocess.Popen(
            [
                "npx",
                "-y",
                "mcp-remote",
                "https://mcp.mpvibe.ru/mcp/analyzer",
                "--header",
                "Authorization: Bearer ${ABCAGE_ANALYZER_TOKEN}",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            bufsize=1,
        )
        self.next_id = 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "codex", "version": "1.0"},
                },
            }
        )
        self._read_id(self.next_id)
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _send(self, msg: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read_id(self, msg_id: int) -> dict:
        assert self.proc.stdout is not None
        deadline = time.time() + 90
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                continue
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("id") == msg_id:
                return data
        raise TimeoutError(f"MCP response timeout for id {msg_id}")

    def query(self, sql: str):
        msg_id = self.next_id
        self.next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "tools/call",
                "params": {"name": "sql__mysql_query", "arguments": {"sql": sql}},
            }
        )
        data = self._read_id(msg_id)
        content = data["result"]["content"][0]["text"]
        if content.startswith("Error:"):
            raise RuntimeError(content)
        return json.loads(content)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def http_json(method: str, url: str, token: str, body=None, timeout=60):
    headers = {"Authorization": token}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except URLError as exc:
        return 0, {"error": str(exc)}


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def ru_day_label(d: date) -> str:
    if d == START:
        return "сегодня"
    if d == START + timedelta(days=1):
        return "завтра"
    if d == START + timedelta(days=2):
        return "послезавтра"
    return d.isoformat()


def normalize_supply(raw: dict, account_id: int, account_name: str) -> dict:
    supply_id = raw.get("supplyID") or raw.get("supplyId") or raw.get("supply_id")
    preorder_id = raw.get("preorderID") or raw.get("preorderId") or raw.get("preorder_id")
    supply_date = raw.get("supplyDate") or raw.get("supply_date") or raw.get("supplied_at")
    status_id = raw.get("statusID") or raw.get("statusId") or raw.get("status_id")
    quantity = raw.get("quantity") or raw.get("details_quantity") or 0
    return {
        "account_id": account_id,
        "account_name": account_name,
        "supply_id": supply_id,
        "preorder_id": preorder_id,
        "supply_date": supply_date[:10] if isinstance(supply_date, str) and supply_date else None,
        "status_id": status_id,
        "quantity": quantity,
        "warehouse_id": raw.get("warehouseID") or raw.get("warehouseId"),
        "warehouse_name": raw.get("warehouseName") or raw.get("warehouse_name"),
        "raw": raw,
    }


def goods_for_supply(token: str, supply: dict):
    base = "https://supplies-api.wildberries.ru/api/v1/supplies"
    attempts = []
    if supply.get("supply_id"):
        attempts.append((supply["supply_id"], False))
    if supply.get("preorder_id"):
        attempts.append((supply["preorder_id"], True))

    for ident, is_preorder in attempts:
        items = []
        offset = 0
        ok = False
        while True:
            qs = urlencode({"limit": 1000, "offset": offset, "isPreorderID": str(is_preorder).lower()})
            status, data = http_json("GET", f"{base}/{ident}/goods?{qs}", token)
            if status == 429:
                time.sleep(2)
                status, data = http_json("GET", f"{base}/{ident}/goods?{qs}", token)
            if status != 200:
                break
            ok = True
            if not isinstance(data, list):
                break
            items.extend(data)
            if len(data) < 1000:
                break
            offset += 1000
        if ok and items:
            return items, {"id": ident, "is_preorder": is_preorder, "status": 200}
    return [], {"id": None, "is_preorder": None, "status": None}


def main():
    db = McpSql()
    try:
        account_rows = db.query(
            """
            SELECT id AS account_id, name AS account_name, account_name_alias,
                   wb_token_supplies, wb_token_v3, wb_token_64, wb_token, token, access_token
            FROM mp.accounts
            WHERE id IN (
                SELECT DISTINCT account_id
                FROM mp.wb_core__supply
                WHERE supplied_at >= '2026-05-21' AND supplied_at < '2026-05-24'
            )
            ORDER BY account_id;
            """
        )

        header_rows = db.query(
            """
            SELECT account_id, supply_id, preorder_id, DATE(supplied_at) AS supply_date,
                   details_quantity, warehouse_name, status_id
            FROM mp.wb_core__supply
            WHERE supplied_at >= '2026-05-21' AND supplied_at < '2026-05-24'
            ORDER BY supplied_at, account_id, supply_id;
            """
        )

        card_rows = db.query(
            """
            SELECT sku, MAX(short_name) AS product_name, MAX(object) AS category
            FROM mp.wb_core__card
            GROUP BY sku;
            """
        )
        stock_rows = db.query(
            """
            SELECT sku, SUM(fbo_real) AS fbo_current
            FROM mp.mp_core__realtime_stocks_data
            WHERE mp = 'wb'
              AND date = (
                  SELECT MAX(date)
                  FROM (
                      SELECT date
                      FROM mp.mp_core__realtime_stocks_data
                      WHERE mp = 'wb'
                      GROUP BY date
                      HAVING SUM(COALESCE(fbo_real, 0)) > 0
                  ) valid_wb_stock_days
              )
            GROUP BY sku;
            """
        )
    finally:
        db.close()

    cards = {str(r["sku"]): r for r in card_rows}
    stocks = {str(r["sku"]): int(float(r["fbo_current"] or 0)) for r in stock_rows}
    headers_by_key = {
        (int(r["account_id"]), int(r["supply_id"]) if r["supply_id"] is not None else None): r
        for r in header_rows
    }

    collected = []
    api_summary = []
    token_fields = ["wb_token_supplies", "wb_token_v3", "wb_token_64", "wb_token", "token", "access_token"]

    def auth_candidates(acc):
        seen = set()
        result = []
        for field in token_fields:
            raw = acc.get(field)
            if not raw:
                continue
            raw = str(raw).strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            result.append((field, "direct", raw))
            if not raw.lower().startswith("bearer "):
                result.append((field, "bearer", f"Bearer {raw}"))
        return result

    for acc in account_rows:
        account_id = int(acc["account_id"])
        account_name = acc.get("account_name_alias") or acc.get("account_name") or f"account {account_id}"
        body = {
            "dates": [{"from": START.isoformat(), "till": END.isoformat(), "type": "supplyDate"}],
            "statusIDs": [1, 2, 3, 4, 5, 6],
        }
        status = None
        data = None
        token = None
        token_source = None
        attempted = []
        for field, mode, candidate in auth_candidates(acc):
            test_status, test_data = http_json(
                "POST",
                "https://supplies-api.wildberries.ru/api/v1/supplies?limit=1000&offset=0",
                candidate,
                body,
            )
            attempted.append({"field": field, "mode": mode, "status": test_status})
            if test_status == 200:
                status, data, token, token_source = test_status, test_data, candidate, f"{field}:{mode}"
                break
            if status is None:
                status, data = test_status, test_data

        api_summary.append(
            {
                "account_id": account_id,
                "account_name": account_name,
                "list_status": status,
                "token_source": token_source,
                "attempted": attempted,
            }
        )
        if status != 200 or not isinstance(data, list):
            api_summary[-1]["error"] = data
            continue
        supplies = [normalize_supply(x, account_id, account_name) for x in data]
        supplies = [
            s
            for s in supplies
            if s.get("supply_date") and START.isoformat() <= s["supply_date"] <= END.isoformat()
        ]
        api_summary[-1]["supplies"] = len(supplies)
        for supply in supplies:
            goods, source = goods_for_supply(token, supply)
            api_summary.append(
                {
                    "account_id": account_id,
                    "supply_id": supply.get("supply_id"),
                    "preorder_id": supply.get("preorder_id"),
                    "supply_date": supply.get("supply_date"),
                    "goods_rows": len(goods),
                    "goods_source": source,
                }
            )
            if not goods:
                continue
            for g in goods:
                nm = g.get("nmID") or g.get("nmId") or g.get("nm_id")
                if nm is None:
                    continue
                sku = str(nm)
                qty = g.get("quantity") or 0
                card = cards.get(sku, {})
                collected.append(
                    {
                        "date": supply["supply_date"],
                        "account_id": account_id,
                        "account_name": account_name,
                        "supply_id": supply.get("supply_id"),
                        "preorder_id": supply.get("preorder_id"),
                        "warehouse_name": supply.get("warehouse_name"),
                        "status_id": supply.get("status_id"),
                        "qty": int(qty or 0),
                        "wb_article": int(nm),
                        "product_name": card.get("product_name") or g.get("vendorCode") or "-",
                        "category": card.get("category") or "-",
                        "fbo_current": stocks.get(sku, 0),
                        "barcode": g.get("barcode"),
                        "vendor_code": g.get("vendorCode"),
                        "accepted_quantity": g.get("acceptedQuantity"),
                        "unloading_quantity": g.get("unloadingQuantity"),
                        "ready_for_sale_quantity": g.get("readyForSaleQuantity"),
                    }
                )

    grouped = defaultdict(lambda: defaultdict(lambda: {"qty": 0, "rows": []}))
    for row in collected:
        key = (row["wb_article"], row["product_name"], row["category"], row["fbo_current"])
        grouped[row["date"]][key]["qty"] += row["qty"]
        grouped[row["date"]][key]["rows"].append(row)

    lines = ["# Поставки FBO WB на ближайшие 3 дня", ""]
    lines.append("_Собрано кастомно через WB Supplies API: список поставок + товары поставки (`/goods`) с fallback по preorderID._")
    lines.append("")
    for idx in range(3):
        d = START + timedelta(days=idx)
        ds = d.isoformat()
        lines.append(f"{ru_day_label(d)} ({fmt_date(d)}):")
        lines.append("")
        lines.append("кол-во к поставке фбо / артикул вб / название товара / категория / остаток фбо текущий")
        lines.append("")
        day_items = grouped.get(ds, {})
        if not day_items:
            day_headers = [r for r in header_rows if str(r["supply_date"])[:10] == ds]
            total_qty = sum(int(r["details_quantity"] or 0) for r in day_headers)
            lines.append(f"_Товарная декомпозиция через WB API не вернулась. В заголовках БД: {len(day_headers)} поставок, {total_qty} шт._")
            lines.append("")
            continue
        sorted_items = sorted(day_items.items(), key=lambda x: (-x[1]["qty"], x[0][0]))
        for (article, name, category, fbo), info in sorted_items:
            lines.append(f"- {info['qty']} / {article} / {name} / {category} / {fbo}")
        lines.append("")

    out_md = ROOT / "pachca_fbo_supplies_custom_2026-05-21.md"
    out_json = ROOT / "pachca_fbo_supplies_custom_2026-05-21.json"
    out_summary = ROOT / "pachca_fbo_supplies_custom_2026-05-21.summary.json"
    out_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    # Strip any accidental API error bodies that could include sensitive metadata.
    safe_summary = []
    for item in api_summary:
        safe = {k: v for k, v in item.items() if k != "error"}
        safe_summary.append(safe)
    out_summary.write_text(json.dumps(safe_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "accounts_checked": len(account_rows),
        "goods_rows": len(collected),
        "md": str(out_md),
        "json": str(out_json),
        "summary": str(out_summary),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
