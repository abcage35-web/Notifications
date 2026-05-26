#!/usr/bin/env node
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT_INCOMPLETE_MD = path.join(ROOT, "Незаполненный контент по Артикулам.md");
const OUT_ALL_CONTENT_MD = path.join(ROOT, "Полный контент по Артикулам.md");
const OUT_RECOMMENDATIONS_MD = path.join(ROOT, "Настройки Рекомендаций Продавца.md");
const SELLER_RECOMMENDATIONS_SCRIPT = path.join(ROOT, "scripts", "build-seller-recommendations-suggestions.mjs");
const SELLER_RECOMMENDATIONS_JSON = path.join(ROOT, "seller-recommendations-suggestions.json");
const BASKET_CACHE_PATH = path.join(ROOT, ".wb-basket-cache.json");
const INCOMPLETE_CONTENT_REPORT_TITLE = "Незаполненный контент по Артикулам";
const INCOMPLETE_CONTENT_MESSAGE_TITLE = `${INCOMPLETE_CONTENT_REPORT_TITLE} (Ежемесячный / 20 число месяца)`;
const MARKETER_MENTIONS = "@a.beaver @a.manokhin @a.nekrasov";
const REPORT_TZ = "Asia/Tbilisi";
const GENERATED_AT_TZ = "Europe/Moscow";
const ANALYZER_URL = "https://mcp.mpvibe.ru/mcp/analyzer";
const MARKETERS_CSV_URL =
  "https://docs.google.com/spreadsheets/d/1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4/export?format=csv&gid=1574673852";
const DESIGNS_CSV_URL =
  "https://docs.google.com/spreadsheets/d/1SNvaHyFSHy9I1rT24dDYsbGEIid5lndcdHEMhTXLjG4/export?format=csv&gid=373432525";
const BASKET_START = 1;
const BASKET_END = 120;
const BASKET_VOL_RANGES = [
  [143, "01"], [287, "02"], [431, "03"], [719, "04"], [1007, "05"],
  [1061, "06"], [1115, "07"], [1169, "08"], [1313, "09"], [1601, "10"],
  [1655, "11"], [1919, "12"], [2045, "13"], [2189, "14"], [2405, "15"],
  [2621, "16"], [2837, "17"], [3053, "18"], [3269, "19"], [3485, "20"],
  [3701, "21"], [3917, "22"], [4133, "23"], [4349, "24"], [4565, "25"],
  [4871, "26"], [5183, "27"], [5439, "28"], [5747, "29"], [6053, "30"],
  [6359, "31"], [6720, "32"], [7023, "33"], [7305, "34"], [7681, "35"],
  [8111, "36"], [8349, "37"], [8669, "38"], [9134, "39"], [9430, "40"],
  [9999, "41"],
];

function executablePath(command) {
  for (const dir of String(process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, command);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      // keep looking
    }
  }
  return command;
}

const NPX = executablePath("npx");

function readAnalyzerToken() {
  if (process.env.ABCAGE_ANALYZER_TOKEN) return process.env.ABCAGE_ANALYZER_TOKEN;
  const configPath = path.join(os.homedir(), ".codex", "config.toml");
  const text = fs.readFileSync(configPath, "utf8");
  const match = text.match(/ABCAGE_ANALYZER_TOKEN\s*=\s*"([^"]+)"/);
  if (!match) throw new Error("ABCAGE_ANALYZER_TOKEN not found");
  return match[1];
}

class McpSql {
  constructor() {
    const env = { ...process.env, ABCAGE_ANALYZER_TOKEN: readAnalyzerToken() };
    this.proc = spawn(
      NPX,
      [
        "-y",
        "mcp-remote",
        ANALYZER_URL,
        "--header",
        "Authorization: Bearer ${ABCAGE_ANALYZER_TOKEN}",
      ],
      { env, stdio: ["pipe", "pipe", "ignore"] },
    );
    this.nextId = 1;
    this.pending = new Map();
    this.rl = readline.createInterface({ input: this.proc.stdout });
    this.rl.on("line", (line) => {
      if (!line.trim().startsWith("{")) return;
      let data;
      try {
        data = JSON.parse(line);
      } catch {
        return;
      }
      if (!data.id || !this.pending.has(data.id)) return;
      const { resolve } = this.pending.get(data.id);
      this.pending.delete(data.id);
      resolve(data);
    });
  }

  async init() {
    await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "codex", version: "1.0" },
    });
    this.notify("notifications/initialized", {});
  }

  request(method, params) {
    const id = this.nextId++;
    const payload = { jsonrpc: "2.0", id, method, params };
    const promise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`MCP response timeout for id ${id}`));
      }, 120_000);
      this.pending.set(id, {
        resolve: (data) => {
          clearTimeout(timeout);
          resolve(data);
        },
      });
    });
    this.proc.stdin.write(`${JSON.stringify(payload)}\n`);
    return promise;
  }

  notify(method, params) {
    this.proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`);
  }

  async query(sql) {
    const data = await this.request("tools/call", {
      name: "sql__mysql_query",
      arguments: { sql },
    });
    const text = data?.result?.content?.[0]?.text || "";
    if (text.startsWith("Error:")) throw new Error(text);
    return JSON.parse(text);
  }

  close() {
    this.rl.close();
    this.proc.kill("SIGTERM");
  }
}

function isoDateOnly(value) {
  return String(value || "").slice(0, 10);
}

function monthStart(dateString) {
  const date = isoDateOnly(dateString);
  return date ? `${date.slice(0, 7)}-01` : "";
}

function nowIso() {
  return new Date().toISOString();
}

function formatMskDateTime(value) {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    timeZone: GENERATED_AT_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.day}.${byType.month}.${byType.year} ${byType.hour}:${byType.minute} МСК`;
}

function todayInTbilisi() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: REPORT_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

function normalizeArticle(value) {
  const article = String(value || "").trim().replace(/\s+/g, "");
  return /^\d+$/.test(article) ? article : "";
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (ch !== "\r") {
      cell += ch;
    }
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  return rows;
}

async function fetchText(url) {
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  return response.text();
}

async function loadMarketers() {
  const rows = parseCsv(await fetchText(MARKETERS_CSV_URL));
  const cabinetByArticle = new Map();
  const marketerByArticle = new Map();

  for (const row of rows.slice(1)) {
    const article = normalizeArticle(row[1]);
    if (!article) continue;
    const cabinet = String(row[2] || "").trim();
    const marketer = String(row[7] || "").trim();
    if (cabinet && !cabinetByArticle.has(article)) cabinetByArticle.set(article, cabinet);
    if (marketer && !marketerByArticle.has(article)) marketerByArticle.set(article, marketer);
  }

  return { cabinetByArticle, marketerByArticle };
}

function extractWbArticles(text) {
  const found = [];
  const re = /https?:\/\/www\.wildberries\.ru\/catalog\/(\d+)(?:\/|\b)/gi;
  let match;
  while ((match = re.exec(String(text || "")))) {
    found.push(match[1]);
  }
  return found;
}

function extractUrls(text) {
  return (String(text || "").match(/https?:\/\/[^\s,;]+/g) || []).map((url) =>
    url.replace(/[)\].,;]+$/, ""),
  );
}

async function loadDesigns() {
  const rows = parseCsv(await fetchText(DESIGNS_CSV_URL));
  const designLinksByArticle = new Map();
  const crmIdsByArticle = new Map();

  for (const row of rows.slice(1)) {
    const crmId = String(row[0] || "").trim();
    const articles = extractWbArticles(row[4]);
    const links = extractUrls(row[18]);
    if (!articles.length) continue;

    for (const article of articles) {
      if (crmId) {
        const crmBucket = crmIdsByArticle.get(article) || [];
        if (!crmBucket.includes(crmId)) crmBucket.push(crmId);
        crmIdsByArticle.set(article, crmBucket);
      }

      if (links.length) {
        const bucket = designLinksByArticle.get(article) || [];
        for (const link of links) {
          if (!bucket.includes(link)) bucket.push(link);
        }
        designLinksByArticle.set(article, bucket);
      }
    }
  }

  return { designLinksByArticle, crmIdsByArticle };
}

async function loadBaseArticlesFromMysql() {
  const db = new McpSql();
  try {
    await db.init();
    const stockDateRows = await db.query(`
      SELECT DATE(MAX(date)) AS stock_date
      FROM mp.mp_core__realtime_stocks_data
      WHERE mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci;
    `);
    const stockDate = isoDateOnly(stockDateRows?.[0]?.stock_date) || todayInTbilisi();
    const planMonth = monthStart(stockDate);

    const rows = await db.query(`
      WITH fbo_by_sku AS (
        SELECT CAST(sku AS UNSIGNED) AS sku_num,
               SUM(COALESCE(fbo_real, 0)) AS fbo
        FROM mp.mp_core__realtime_stocks_data
        WHERE date = '${stockDate}'
          AND mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
          AND sku REGEXP '^[0-9]+$'
        GROUP BY sku_num
      ),
      plan_by_sku AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               SUM(COALESCE(plan.correct_count, plan.planned_count, 0)) AS plan_qty
        FROM mp.wb_core__card card
        JOIN mp.mp_core__sales_plan plan
          ON plan.card_id = card.card_id
         AND plan.account_id = card.account_id
         AND plan.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
         AND plan.planning_date = '${planMonth}'
        WHERE card.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num
      ),
      unioned AS (
        SELECT sku_num, plan_qty, 0 AS fbo FROM plan_by_sku
        UNION ALL
        SELECT sku_num, 0 AS plan_qty, fbo FROM fbo_by_sku
      )
      SELECT CAST(sku_num AS CHAR) AS article,
             SUM(plan_qty) AS plan_qty,
             SUM(fbo) AS fbo
      FROM unioned
      GROUP BY sku_num
      HAVING plan_qty > 10 OR fbo > 10
      ORDER BY sku_num;
    `);

    const baseByArticle = new Map(
      rows.map((row) => [
        normalizeArticle(row.article),
        {
          article: normalizeArticle(row.article),
          planQty: Number(row.plan_qty || 0),
          fbo: Number(row.fbo || 0),
        },
      ]),
    );
    return { stockDate, planMonth, baseByArticle };
  } finally {
    db.close();
  }
}

async function fetchWithTimeout(url, timeoutMs = 2_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function readBasketCache() {
  try {
    const entries = Object.entries(JSON.parse(fs.readFileSync(BASKET_CACHE_PATH, "utf8")));
    return new Map(entries.filter(([vol, suffix]) => /^\d+$/.test(vol) && /^\d{2}$/.test(String(suffix))));
  } catch {
    return new Map();
  }
}

function writeBasketCache(cache) {
  const sorted = Object.fromEntries([...cache.entries()].sort((a, b) => Number(a[0]) - Number(b[0])));
  fs.writeFileSync(BASKET_CACHE_PATH, `${JSON.stringify(sorted, null, 2)}\n`, "utf8");
}

const basketHostByVol = readBasketCache();
let basketCacheDirty = false;

function basketSuffixForVol(vol) {
  return BASKET_VOL_RANGES.find(([maxVol]) => vol <= maxVol)?.[1] || "";
}

function candidateBasketSuffixes(vol) {
  const suffixes = [];
  const add = (value) => {
    const num = Number(value);
    if (!Number.isInteger(num) || num < BASKET_START || num > BASKET_END) return;
    const suffix = String(num).padStart(2, "0");
    if (!suffixes.includes(suffix)) suffixes.push(suffix);
  };

  add(basketHostByVol.get(String(vol)));
  add(basketSuffixForVol(vol));
  for (const delta of [-1, 1, -2, 2]) add(Number(basketSuffixForVol(vol)) + delta);
  for (let host = BASKET_START; host <= BASKET_END; host += 1) add(host);
  return suffixes;
}

async function loadCardJson(article) {
  const nmId = Number(article);
  if (!Number.isInteger(nmId) || nmId <= 0) return null;
  const vol = Math.floor(nmId / 100000);
  const part = Math.floor(nmId / 1000);

  const tryHost = async (suffix) => {
    const url = `https://basket-${suffix}.wbbasket.ru/vol${vol}/part${part}/${nmId}/info/ru/card.json`;
    try {
      const response = await fetchWithTimeout(url);
      if (!response.ok) return null;
      const card = await response.json();
      return Number(card?.nm_id) === nmId ? card : null;
    } catch {
      return null;
    }
  };

  for (const suffix of candidateBasketSuffixes(vol)) {
    const card = await tryHost(suffix);
    if (card) {
      if (basketHostByVol.get(String(vol)) !== suffix) {
        basketHostByVol.set(String(vol), suffix);
        basketCacheDirty = true;
      }
      return card;
    }
  }

  return null;
}

async function mapLimit(items, limit, mapper) {
  const result = new Array(items.length);
  let index = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (index < items.length) {
      const current = index;
      index += 1;
      result[current] = await mapper(items[current], current);
    }
  });
  await Promise.all(workers);
  return result;
}

async function loadCardsByArticle(articles) {
  const entries = await mapLimit(articles, 8, async (article, index) => {
    if ((index + 1) % 20 === 0 || index === articles.length - 1) {
      process.stderr.write(`WB card.json: ${index + 1}/${articles.length}\n`);
    }
    return [article, await loadCardJson(article)];
  });
  if (basketCacheDirty) writeBasketCache(basketHostByVol);
  return new Map(entries);
}

function buildContentRowsFromOpenWb(baseByArticle, cardsByArticle) {
  return [...baseByArticle.values()]
    .sort((a, b) => Number(a.article) - Number(b.article))
    .map((item) => {
      const card = cardsByArticle.get(item.article);
      return {
        article: item.article,
        nm_id: item.article,
        product_name: String(card?.imt_name || card?.slug || "").trim(),
        category_name: String(card?.subj_name || "").trim(),
        stock_value: item.fbo,
        has_recommendations: card?.has_seller_recommendations === true ? 1 : 0,
        has_rich: card?.has_rich === true ? 1 : 0,
        has_video: card?.media?.has_video === true ? 1 : 0,
        sort_index: 0,
        cabinet: "",
      };
    });
}

function filterProblemRows(rows) {
  return rows.filter((row) =>
    Number(row.has_recommendations) !== 1 ||
    Number(row.has_rich) === 0 ||
    Number(row.has_video) !== 1,
  );
}

function mdEscape(value) {
  return String(value ?? "")
    .replace(/\r?\n/g, " ")
    .replace(/\|/g, "\\|")
    .trim();
}

function valueOrDash(value) {
  const text = mdEscape(value);
  return text || "-";
}

function articleLink(article) {
  return `[${article}](https://www.wildberries.ru/catalog/${article}/detail.aspx)`;
}

function fmtInt(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0";
  return String(Math.round(num));
}

function designMarkdown(links) {
  if (!links?.length) return "-";
  if (links.length === 1) return `[дизайн](${links[0]})`;
  return links.map((link, index) => `[дизайн ${index + 1}](${link})`).join(", ");
}

function crmIdText(ids) {
  if (!ids?.length) return "-";
  return ids.map((id) => valueOrDash(id)).join(", ");
}

function problemByFlag(value, rich = false) {
  if (rich) return Number(value) === 0 ? "да" : "-";
  return Number(value) === 1 ? "-" : "да";
}

function fboStockText(baseByArticle, article) {
  const stock = baseByArticle.get(article)?.fbo;
  return Number.isFinite(stock) ? String(Math.round(stock)) : "-";
}

function loadRecommendationDetails() {
  execFileSync(process.execPath, [SELLER_RECOMMENDATIONS_SCRIPT], {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 30 * 1024 * 1024,
    stdio: ["ignore", "pipe", "inherit"],
  });

  const payload = JSON.parse(fs.readFileSync(SELLER_RECOMMENDATIONS_JSON, "utf8"));
  const byKey = new Map();
  const byArticle = new Map();
  for (const row of payload.rows || []) {
    const article = normalizeArticle(row.article);
    if (!article) continue;
    const cabinet = String(row.cabinet || "-").trim() || "-";
    const normalized = { ...row, article, cabinet };
    byKey.set(`${cabinet}::${article}`, normalized);
    if (!byArticle.has(article)) byArticle.set(article, normalized);
  }
  return { payload, byKey, byArticle };
}

function recommendedCategoriesText(categories) {
  if (!categories?.length) return "-";
  return categories.map((item) => valueOrDash(item.category || item)).join(", ");
}

function recommendationCandidateText(candidates) {
  if (!candidates?.length) return "-";
  return candidates
    .map((candidate) => {
      const parts = [
        valueOrDash(candidate.category),
        `FBO ${fmtInt(candidate.fbo)}`,
        `30д ${fmtInt(candidate.orders30d)}`,
      ];
      return `${articleLink(candidate.article)} (${parts.join(", ")})`;
    })
    .join("<br>");
}

function buildRecommendationDetailRows({
  rows,
  baseByArticle,
  cabinetByArticle,
  cardsByArticle,
  recommendationDetails,
}) {
  return rows
    .filter((row) => problemByFlag(row.has_recommendations) === "да")
    .map((row) => {
      const article = row.article;
      const cabinetFromSheet = String(cabinetByArticle.get(article) || "").trim();
      const detail =
        recommendationDetails.byKey.get(`${cabinetFromSheet}::${article}`) ||
        recommendationDetails.byArticle.get(article);
      if (detail) {
        return [
          valueOrDash(detail.cabinet),
          articleLink(article),
          valueOrDash(detail.category),
          valueOrDash(detail.productName),
          fmtInt(detail.fbo),
          fmtInt(detail.planQty),
          fmtInt(detail.orders30d),
          recommendedCategoriesText(detail.recommendedCategories),
          recommendationCandidateText(detail.candidates),
          valueOrDash(detail.why),
        ];
      }

      const card = cardsByArticle.get(article);
      const base = baseByArticle.get(article);
      const productName = row.product_name || card?.imt_name || card?.slug || "-";
      const category = row.category_name || card?.subj_name || "-";
      return [
        valueOrDash(cabinetFromSheet),
        articleLink(article),
        valueOrDash(category),
        valueOrDash(productName),
        fboStockText(baseByArticle, article),
        fmtInt(base?.planQty),
        "-",
        "-",
        "-",
        "Не найдено в расчете рекомендаций: проверить кабинет/категорию и наличие товаров-кандидатов с FBO > 10 внутри кабинета.",
      ];
    });
}

function groupProblemSummary(tableRows) {
  const segmentByCabinet = (cabinet) => {
    if (["Паша 1", "Стас 1"].includes(cabinet)) return "Паша 1 + Стас 1";
    if (["Паша 2", "Стас 2"].includes(cabinet)) return "Паша 2 + Стас 2";
    return cabinet;
  };
  const segmentOrder = new Map([
    ["Паша 1 + Стас 1", 1],
    ["Паша 2 + Стас 2", 2],
  ]);
  const grouped = new Map();
  for (const cells of tableRows) {
    const marketer = cells[8] && cells[8] !== "-" ? cells[8] : "Без маркетолога";
    const cabinet = cells[7] && cells[7] !== "-" ? cells[7] : "Без ИП";
    const segment = segmentByCabinet(cabinet);
    const key = `${marketer}\u0000${segment}`;
    const current = grouped.get(key) || {
      marketer,
      segment,
      recommendations: 0,
      rich: 0,
      video: 0,
      totalRows: 0,
    };
    current.totalRows += 1;
    if (cells[9] === "да") current.recommendations += 1;
    if (cells[10] === "да") current.rich += 1;
    if (cells[11] === "да") current.video += 1;
    grouped.set(key, current);
  }

  const byMarketer = new Map();
  for (const row of grouped.values()) {
    if (!byMarketer.has(row.marketer)) byMarketer.set(row.marketer, []);
    byMarketer.get(row.marketer).push(row);
  }

  return [...byMarketer.entries()]
    .map(([marketer, rows]) => ({
      marketer,
      rows: rows.sort((a, b) => {
        const orderDelta = (segmentOrder.get(a.segment) || 99) - (segmentOrder.get(b.segment) || 99);
        return orderDelta || a.segment.localeCompare(b.segment, "ru");
      }),
      totalProblems: rows.reduce((sum, row) => sum + row.recommendations + row.rich + row.video, 0),
    }))
    .sort((a, b) => a.marketer.localeCompare(b.marketer, "ru"));
}

function buildPachcaMessage({ tableRows, generatedAt, stockDate, planMonth }) {
  const grouped = groupProblemSummary(tableRows);
  const generatedAtText = formatMskDateTime(generatedAt);
  const totals = tableRows.reduce(
    (acc, cells) => {
      if (cells[9] === "да") acc.recommendations += 1;
      if (cells[10] === "да") acc.rich += 1;
      if (cells[11] === "да") acc.video += 1;
      return acc;
    },
    { recommendations: 0, rich: 0, video: 0 },
  );

  const lines = [
    `**${INCOMPLETE_CONTENT_MESSAGE_TITLE}**`,
    MARKETER_MENTIONS,
    "",
    `_Сформировано: ${generatedAtText}_`,
    `_Фильтр: план продаж за ${planMonth.slice(0, 7)} > 10 или FBO > 10 на ${stockDate}._`,
    "",
    "**Инструкции маркетологам:**",
    `1. Поставить задачу Ассистенту в Яндекс Трекере, передав на вход файл \`${path.basename(OUT_INCOMPLETE_MD)}\`.`,
    "•• Выбрать ответственного за создание одной общей задачи или действовать по плану очередности ответственных.",
    "•• При необходимости скорректировать запрос: добавить или убрать отдельные артикулы.",
    `2. Использовать файл \`${path.basename(OUT_ALL_CONTENT_MD)}\` для соединения с отчетом \`Список товаров по Выручке ПП\`.`,
    `3. Скорректировать рекомендации продавца по файлу \`${path.basename(OUT_RECOMMENDATIONS_MD)}\`.`,
    `4. Проконтролировать выполнение задачи Ассистентом по файлу \`${path.basename(OUT_INCOMPLETE_MD)}\`.`,
    "",
    "**Сводка:**",
    `• Всего товаров в файле: ${tableRows.length}`,
    `• Проблема рекомендация: ${totals.recommendations}`,
    `• Проблема рич: ${totals.rich}`,
    `• Проблема видео: ${totals.video}`,
  ];

  return lines.join("\n");
}

function buildPachcaMarketerSummaryMessage(tableRows) {
  const grouped = groupProblemSummary(tableRows);
  const lines = [
    "**Сводка по маркетологам / кабинетам / ошибкам:**",
  ];

  for (const group of grouped) {
    const visibleRows = group.rows
      .map((row) => ({
        ...row,
        problemLines: [
          ["Проблема рекомендация", row.recommendations],
          ["Проблема рич", row.rich],
          ["Проблема видео", row.video],
        ].filter(([, count]) => count > 0),
      }))
      .filter((row) => row.problemLines.length > 0);
    if (!visibleRows.length) continue;

    const marketerTitle =
      group.marketer === "Без маркетолога"
        ? `Без маркетолога: ${MARKETER_MENTIONS}`
        : group.marketer;
    lines.push(`**${marketerTitle}**`);
    for (const row of visibleRows) {
      lines.push(`• **${row.segment}**`);
      for (const [label, count] of row.problemLines) {
        lines.push(`•• ${label}: ${count}`);
      }
    }
    lines.push("");
  }

  return lines.join("\n");
}

function buildPachcaThreadMessage() {
  return [
    "**Описание файлов:**",
    `• \`${path.basename(OUT_RECOMMENDATIONS_MD)}\`: детализация по настройке рекомендаций продавца; проблемные артикулы, подходящие категории и товары для рекомендательного блока.`,
    `• \`${path.basename(OUT_INCOMPLETE_MD)}\`: только артикулы с незаполненным контентом по рекомендациям, рич-контенту или видео.`,
    `• \`${path.basename(OUT_ALL_CONTENT_MD)}\`: все артикулы из базового фильтра, включая товары без проблем, с теми же колонками и статусами контента.`,
  ].join("\n");
}

function buildMarkdown({
  rows,
  allRows,
  baseByArticle,
  stockDate,
  cabinetByArticle,
  marketerByArticle,
  designLinksByArticle,
  crmIdsByArticle,
  cardsByArticle,
  recommendationDetails,
  planMonth,
  generatedAt,
}) {
  const generatedAtText = formatMskDateTime(generatedAt);
  const buildContentTableRows = (sourceRows) => sourceRows.map((row) => {
    const article = row.article;
    const card = cardsByArticle.get(article);
    const brand = String(card?.selling?.brand_name || "").trim();
    const productName = row.product_name || card?.imt_name || card?.slug || "-";
    const category = row.category_name || card?.subj_name || "-";
    return [
      crmIdText(crmIdsByArticle.get(article)),
      articleLink(article),
      designMarkdown(designLinksByArticle.get(article)),
      valueOrDash(productName),
      valueOrDash(brand),
      fboStockText(baseByArticle, article),
      valueOrDash(category),
      valueOrDash(cabinetByArticle.get(article)),
      valueOrDash(marketerByArticle.get(article)),
      problemByFlag(row.has_recommendations),
      problemByFlag(row.has_rich, true),
      problemByFlag(row.has_video),
    ];
  });

  const tableRows = buildContentTableRows(rows);
  const allContentTableRows = buildContentTableRows(allRows);
  const recommendationDetailRows = buildRecommendationDetailRows({
    rows,
    baseByArticle,
    cabinetByArticle,
    cardsByArticle,
    recommendationDetails,
  });

  const baseStats = [...baseByArticle.values()].reduce(
    (acc, item) => {
      if (item.planQty > 10) acc.withPlan += 1;
      if (item.fbo > 10) acc.withFbo += 1;
      if (item.planQty > 10 && item.fbo > 10) acc.withBoth += 1;
      return acc;
    },
    { withPlan: 0, withFbo: 0, withBoth: 0 },
  );

  const problemTotals = (sourceRows) => sourceRows.reduce(
    (acc, cells) => {
      if (cells[9] === "да") acc.recommendations += 1;
      if (cells[10] === "да") acc.rich += 1;
      if (cells[11] === "да") acc.video += 1;
      if (cells[9] === "-" && cells[10] === "-" && cells[11] === "-") acc.withoutProblems += 1;
      return acc;
    },
    { recommendations: 0, rich: 0, video: 0, withoutProblems: 0 },
  );

  const problemSummary = problemTotals(tableRows);
  const allContentSummary = problemTotals(allContentTableRows);
  const tableHeader = [
    "| CRM ID | Артикул | Дизайн | Название товара | Бренд | Остаток FBO | Категория | Кабинет | Маркетолог | Проблема рекомендации | Проблема рич-контент | Проблема видео |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|",
  ];
  const hints = [
    "| **Подсказки для Ассистента** |",
    "|---|",
    "| 1. **Ссылка на дизайн:** если ссылки на дизайн нет или она неверная, запросить у отдела Контента добавление корректной ссылки на папку дизайна товара в CRM по CRM ID.<br>2. **Рич / видео:** если отсутствует папка какого-то носителя, поставить задачу отделу Контента на разработку этих носителей; можно одной задачей на весь список.<br>3. **Видео:** если видео нет, использовать анимацию. Лучший формат видео - анимация + видео. |",
  ];
  const exportBlock = (items) => [
    "| **Выгрузка** |",
    "|---|",
    `| ${items.map((item) => `- ${item}`).join("<br>")} |`,
  ];

  const notes = (filterLines) => [
    "## Примечания",
    "",
    ...filterLines,
    "",
    `**База отбора:** всего ${baseByArticle.size} артикулов; с планом продаж ${baseStats.withPlan}; с FBO > 10 ${baseStats.withFbo}; одновременно с планом и FBO > 10 ${baseStats.withBoth}.`,
    "",
    "**Статусы проблем:** открытый WB `card.json` по артикулу: `has_seller_recommendations`, `has_rich`, `media.has_video`.",
    "",
    "**CRM ID:** значение из Google Sheets потока дизайнов, колонка A по WB-артикулу из ссылок www.wildberries.ru в колонке E.",
    "",
    "**Маркетолог:** тег из Google Sheets, колонка H по артикулу из колонки B.",
    "",
    "**Кабинет:** значение из Google Sheets, колонка C по артикулу из колонки B.",
    "",
    "**Дизайн:** ссылка из Google Sheets, колонка S по WB-артикулу из ссылок www.wildberries.ru в колонке E.",
    "",
    "**Бренд:** значение из WB card.json, поле selling.brand_name; если бренд не указан, стоит прочерк.",
    "",
    `**Остаток FBO:** сумма fbo_real из нашей БД \`mp.mp_core__realtime_stocks_data\` по WB-артикулу на ${stockDate}.`,
    "",
    "**Артикул:** markdown-ссылка на WB-карточку вида https://www.wildberries.ru/catalog/{артикул}/detail.aspx.",
    "",
  ];

  const markdownLines = [
    `# ${INCOMPLETE_CONTENT_REPORT_TITLE}`,
    "",
    "> **Сформировано:** " + generatedAtText,
    "",
    ...hints,
    "",
    ...exportBlock([
      `Всего товаров: ${tableRows.length}`,
      `Проблема рекомендации: ${problemSummary.recommendations}`,
      `Проблема рич: ${problemSummary.rich}`,
      `Проблема видео: ${problemSummary.video}`,
    ]),
    "",
    ...tableHeader,
    ...tableRows.map((cells) => `| ${cells.join(" | ")} |`),
    "",
    ...notes([
      `**Фильтр базового списка:** артикулы из основной базы, где план продаж за месяц ${planMonth.slice(0, 7)} > 10 или FBO-остаток на ${stockDate} > 10.`,
      "",
      "**Фильтр проблем:** есть хотя бы одна проблема среди рекомендаций, рич-контента или видео.",
    ]),
  ];

  const allContentMarkdownLines = [
    "# Полный контент по Артикулам",
    "",
    "> **Сформировано:** " + generatedAtText,
    "",
    ...hints,
    "",
    ...exportBlock([
      `Всего товаров: ${allContentTableRows.length}`,
      `Без проблем: ${allContentSummary.withoutProblems}`,
      `Проблема рекомендации: ${allContentSummary.recommendations}`,
      `Проблема рич: ${allContentSummary.rich}`,
      `Проблема видео: ${allContentSummary.video}`,
    ]),
    "",
    ...tableHeader,
    ...allContentTableRows.map((cells) => `| ${cells.join(" | ")} |`),
    "",
    ...notes([
      `**Фильтр базового списка:** все артикулы из основной базы, где план продаж за месяц ${planMonth.slice(0, 7)} > 10 или FBO-остаток на ${stockDate} > 10.`,
      "",
      "**Фильтр проблем:** не применяется; в таблицу включены товары и с проблемами, и без проблем.",
    ]),
  ];

  return {
    markdown: markdownLines.join("\n"),
    allContentMarkdown: allContentMarkdownLines.join("\n"),
    tableRows,
    allContentTableRows,
    recommendationDetailRows,
  };
}

function validateContentRows(tableRows, label) {
  const errors = [];
  for (const [index, cells] of tableRows.entries()) {
    if (cells.length !== 12) errors.push(`${label} row ${index + 1}: expected 12 cells, got ${cells.length}`);
    for (const problemIndex of [9, 10, 11]) {
      if (!["да", "-"].includes(cells[problemIndex])) {
        errors.push(`${label} row ${index + 1}: invalid problem value ${cells[problemIndex]}`);
      }
    }
    if (!/^-?\d+$|^-$/u.test(cells[5])) {
      errors.push(`${label} row ${index + 1}: invalid FBO stock ${cells[5]}`);
    }
  }
  return errors;
}

function validate(tableRows, allContentTableRows, recommendationDetailRows) {
  const errors = [
    ...validateContentRows(tableRows, "incomplete"),
    ...validateContentRows(allContentTableRows, "all-content"),
  ];
  for (const [index, cells] of recommendationDetailRows.entries()) {
    if (cells.length !== 10) errors.push(`recommendation row ${index + 1}: expected 10 cells, got ${cells.length}`);
  }
  if (errors.length) {
    throw new Error(`Validation failed:\n${errors.slice(0, 20).join("\n")}`);
  }
}

async function main() {
  const generatedAt = nowIso();
  const { stockDate, planMonth, baseByArticle } = await loadBaseArticlesFromMysql();
  const cardArticles = [...baseByArticle.keys()];

  process.stderr.write(`Base articles: ${baseByArticle.size}\n`);
  const [marketers, designs, cardsByArticle] = await Promise.all([
    loadMarketers(),
    loadDesigns(),
    loadCardsByArticle(cardArticles),
  ]);
  const allRows = buildContentRowsFromOpenWb(baseByArticle, cardsByArticle);
  const problemRows = filterProblemRows(allRows);
  process.stderr.write(`Problem rows after WB card.json filter: ${problemRows.length}\n`);
  process.stderr.write(`All base rows: ${allRows.length}\n`);
  const recommendationDetails = loadRecommendationDetails();
  process.stderr.write(`Recommendation detail rows: ${recommendationDetails.payload.rows.length}\n`);

  const { markdown, allContentMarkdown, tableRows, allContentTableRows, recommendationDetailRows } = buildMarkdown({
    rows: problemRows,
    allRows,
    baseByArticle,
    stockDate,
    cabinetByArticle: marketers.cabinetByArticle,
    marketerByArticle: marketers.marketerByArticle,
    designLinksByArticle: designs.designLinksByArticle,
    crmIdsByArticle: designs.crmIdsByArticle,
    cardsByArticle,
    recommendationDetails,
    planMonth,
    generatedAt,
  });

  validate(tableRows, allContentTableRows, recommendationDetailRows);
  fs.writeFileSync(OUT_INCOMPLETE_MD, markdown, "utf8");
  fs.writeFileSync(OUT_ALL_CONTENT_MD, allContentMarkdown, "utf8");
  const pachcaMessage = buildPachcaMessage({ tableRows, generatedAt, stockDate, planMonth });
  const pachcaThreadMessage = buildPachcaThreadMessage();
  const pachcaMarketerSummaryMessage = buildPachcaMarketerSummaryMessage(tableRows);
  process.stdout.write(
    JSON.stringify(
      {
        incompleteOut: OUT_INCOMPLETE_MD,
        allContentOut: OUT_ALL_CONTENT_MD,
        recommendationsOut: OUT_RECOMMENDATIONS_MD,
        pachcaMessage,
        pachcaThreadMessage,
        pachcaMarketerSummaryMessage,
        baseArticles: baseByArticle.size,
        problemRows: problemRows.length,
        allBaseRows: allRows.length,
        recommendationProblemRows: recommendationDetailRows.length,
        stockDate,
        planMonth,
      },
      null,
      2,
    ) + "\n",
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
