#!/usr/bin/env node
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT_MD = path.join(ROOT, "Настройки Рекомендаций Продавца.md");
const OUT_JSON = path.join(ROOT, "seller-recommendations-suggestions.json");
const REPORT_TZ = "Asia/Tbilisi";
const GENERATED_AT_TZ = "Europe/Moscow";
const ANALYZER_URL = "https://mcp.mpvibe.ru/mcp/analyzer";
const MAX_ARTICLES_PER_TARGET = 6;
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

function addDays(dateString, days) {
  const date = new Date(`${dateString}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function monthStart(dateString) {
  const date = isoDateOnly(dateString);
  return date ? `${date.slice(0, 7)}-01` : "";
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

function normalizeArticle(value) {
  const article = String(value || "").trim().replace(/\s+/g, "");
  return /^\d+$/.test(article) ? article : "";
}

function normalizeCabinet(value) {
  const text = String(value || "").trim();
  if (text === "ИП Карпачев") return "Паша 1";
  if (text === "ИП Сытин") return "Стас 1";
  return text || "-";
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

function fmtInt(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0";
  return String(Math.round(num));
}

function articleLink(article) {
  return `[${article}](https://www.wildberries.ru/catalog/${article}/detail.aspx)`;
}

function key(cabinet, article) {
  return `${cabinet}::${article}`;
}

async function loadMetricsFromMysql() {
  const db = new McpSql();
  try {
    await db.init();
    const stockRows = await db.query(`
      SELECT DATE(MAX(date)) AS stock_date
      FROM mp.mp_core__realtime_stocks_data
      WHERE mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci;
    `);
    const stockDate = isoDateOnly(stockRows?.[0]?.stock_date) || todayInTbilisi();
    const planMonth = monthStart(stockDate);
    const ordersTo = addDays(stockDate, -1);
    const ordersFrom = addDays(ordersTo, -29);

    const rows = await db.query(`
      WITH card_info AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               card.account_id,
               MAX(COALESCE(card.short_name, card.name)) AS product_name,
               MAX(card.object) AS category,
               MAX(card.card_id) AS card_id
        FROM mp.wb_core__card card
        WHERE card.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, card.account_id
      ),
      stock AS (
        SELECT CAST(sku AS UNSIGNED) AS sku_num,
               account_id,
               SUM(COALESCE(fbo_real, 0)) AS fbo
        FROM mp.mp_core__realtime_stocks_data
        WHERE date = '${stockDate}'
          AND mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
          AND sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, account_id
      ),
      plans AS (
        SELECT CAST(card.sku AS UNSIGNED) AS sku_num,
               card.account_id,
               SUM(COALESCE(plan.correct_count, plan.planned_count, 0)) AS plan_qty
        FROM mp.wb_core__card card
        JOIN mp.mp_core__sales_plan plan
          ON plan.card_id = card.card_id
         AND plan.account_id = card.account_id
         AND plan.mp COLLATE utf8mb4_unicode_ci = 'wb' COLLATE utf8mb4_unicode_ci
         AND plan.planning_date = '${planMonth}'
        WHERE card.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, card.account_id
      ),
      orders AS (
        SELECT CAST(f.sku AS UNSIGNED) AS sku_num,
               f.account_id,
               SUM(COALESCE(f.orders_count, 0)) AS orders_30d,
               SUM(COALESCE(f.orders_sum, 0)) AS revenue_30d,
               SUM(COALESCE(f.open_card_count, 0)) AS open_card_30d
        FROM mp.wb_core__funnel f
        WHERE f.date_at BETWEEN '${ordersFrom}' AND '${ordersTo}'
          AND f.sku REGEXP '^[0-9]+$'
        GROUP BY sku_num, f.account_id
      )
      SELECT COALESCE(account.account_name_alias, account.name) AS cabinet,
             CAST(ci.sku_num AS CHAR) AS article,
             MAX(ci.product_name) AS product_name,
             MAX(ci.category) AS category,
             SUM(COALESCE(stock.fbo, 0)) AS fbo,
             SUM(COALESCE(plans.plan_qty, 0)) AS plan_qty,
             SUM(COALESCE(orders.orders_30d, 0)) AS orders_30d,
             SUM(COALESCE(orders.revenue_30d, 0)) AS revenue_30d,
             SUM(COALESCE(orders.open_card_30d, 0)) AS open_card_30d
      FROM card_info ci
      LEFT JOIN mp.accounts account ON account.id = ci.account_id
      LEFT JOIN stock ON stock.sku_num = ci.sku_num AND stock.account_id = ci.account_id
      LEFT JOIN plans ON plans.sku_num = ci.sku_num AND plans.account_id = ci.account_id
      LEFT JOIN orders ON orders.sku_num = ci.sku_num AND orders.account_id = ci.account_id
      GROUP BY cabinet, ci.sku_num
      HAVING fbo > 0 OR plan_qty > 0 OR orders_30d > 0
      ORDER BY cabinet, ci.sku_num;
    `);

    const metrics = rows.map((row) => ({
      cabinet: normalizeCabinet(row.cabinet),
      article: normalizeArticle(row.article),
      productName: String(row.product_name || "").trim(),
      category: String(row.category || "").trim(),
      fbo: Number(row.fbo || 0),
      planQty: Number(row.plan_qty || 0),
      orders30d: Number(row.orders_30d || 0),
      revenue30d: Number(row.revenue_30d || 0),
      openCard30d: Number(row.open_card_30d || 0),
    })).filter((row) => row.article && row.cabinet !== "-");

    return { stockDate, planMonth, ordersFrom, ordersTo, metrics };
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

const basketHostByVol = new Map();

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
      basketHostByVol.set(String(vol), suffix);
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
  return new Map(entries);
}

const CATEGORY_GROUPS = {
  pool: [
    "Бассейны надувные",
    "Бассейны каркасные",
    "Матрасы для плавания",
    "Круги для плавания",
    "Аксессуары для бассейна",
    "Тенты для бассейнов",
    "Скиммеры",
    "Лестницы для бассейнов",
  ],
  fitness: [
    "Массажеры электрические",
    "Массажеры косметические",
    "Аксессуары для массажеров",
    "Ролики массажные",
    "Тренажеры",
    "Коврики спортивные",
    "Блоки для йоги",
    "Фитболы",
    "Беговые дорожки",
  ],
  weights: ["Гантели", "Грифы", "Диски для штанг и гантелей", "Зажимы на гриф", "Штанги"],
  sleep: ["Одеяла", "Подушки ортопедические"],
  school: ["Рюкзаки", "Пеналы", "Рубашки", "Колготки"],
  toys: [
    "Игровые наборы",
    "Сюжетные игровые наборы",
    "Игровые палатки",
    "Игровые коврики",
    "Игрушечная посуда",
    "Конструкторы",
    "Радиоуправляемые игрушки",
    "Автотреки",
    "Железные дороги",
    "Куклы",
    "Кукольные домики",
    "Роботы",
    "Настольные игры для детей",
    "Наборы для лепки",
    "Наборы для рисования",
    "Наборы для поделок",
    "Коврики детские",
  ],
  home: ["Швабры", "Этажерки", "Вешалки напольные", "Вешалки-плечики", "Стулья", "Кресла компьютерные"],
  garden: ["Опрыскиватели", "Кусторезы", "Электропилы цепные"],
  appliance: ["Триммеры", "Упаковщики вакуумные", "Ирригаторы", "Увлажнители", "Отпариватели"],
};

const DIRECT_CATEGORY_RULES = [
  {
    match: ["Бассейны надувные", "Бассейны каркасные"],
    recommend: ["Бассейны каркасные", "Бассейны надувные", "Аксессуары для бассейна", "Тенты для бассейнов", "Скиммеры", "Лестницы для бассейнов", "Матрасы для плавания", "Круги для плавания"],
    reason: "допродажа к бассейнам",
  },
  {
    match: ["Матрасы для плавания", "Круги для плавания"],
    recommend: ["Бассейны надувные", "Бассейны каркасные", "Аксессуары для бассейна", "Тенты для бассейнов"],
    reason: "сезонная связка для плавания",
  },
  {
    match: ["Аксессуары для бассейна", "Скиммеры", "Тенты для бассейнов", "Лестницы для бассейнов"],
    recommend: ["Бассейны надувные", "Бассейны каркасные", "Матрасы для плавания", "Круги для плавания", "Аксессуары для бассейна"],
    reason: "комплектующие и основные товары для бассейнов",
  },
  {
    match: ["Массажеры электрические", "Массажеры косметические", "Аксессуары для массажеров"],
    recommend: ["Массажеры электрические", "Ролики массажные", "Тренажеры", "Коврики спортивные", "Блоки для йоги", "Фитболы"],
    reason: "здоровье, массаж и восстановление",
  },
  {
    match: ["Ролики массажные", "Коврики спортивные", "Блоки для йоги", "Фитболы"],
    recommend: ["Ролики массажные", "Коврики спортивные", "Блоки для йоги", "Фитболы", "Тренажеры", "Гантели"],
    reason: "фитнес и восстановление",
  },
  {
    match: ["Гантели", "Грифы", "Диски для штанг и гантелей", "Зажимы на гриф", "Штанги"],
    recommend: ["Гантели", "Грифы", "Диски для штанг и гантелей", "Зажимы на гриф", "Коврики спортивные", "Тренажеры"],
    reason: "силовой инвентарь и аксессуары",
  },
  {
    match: ["Тренажеры", "Беговые дорожки"],
    recommend: ["Тренажеры", "Беговые дорожки", "Коврики спортивные", "Гантели", "Ролики массажные", "Фитболы"],
    reason: "домашний фитнес",
  },
  {
    match: ["Одеяла", "Подушки ортопедические"],
    recommend: ["Одеяла", "Подушки ортопедические"],
    reason: "сон и соседние размеры/веса",
  },
  {
    match: ["Рюкзаки", "Пеналы", "Рубашки", "Колготки"],
    recommend: ["Рюкзаки", "Пеналы", "Рубашки", "Колготки"],
    reason: "школьная корзина",
  },
  {
    match: CATEGORY_GROUPS.toys,
    recommend: CATEGORY_GROUPS.toys,
    reason: "смежные детские игрушки",
  },
  {
    match: CATEGORY_GROUPS.home,
    recommend: CATEGORY_GROUPS.home,
    reason: "товары для дома внутри кабинета",
  },
  {
    match: CATEGORY_GROUPS.garden,
    recommend: CATEGORY_GROUPS.garden,
    reason: "садовая техника и инвентарь",
  },
  {
    match: CATEGORY_GROUPS.appliance,
    recommend: CATEGORY_GROUPS.appliance,
    reason: "мелкая техника и уход",
  },
];

function groupForCategory(category) {
  for (const [group, categories] of Object.entries(CATEGORY_GROUPS)) {
    if (categories.includes(category)) return group;
  }
  return "";
}

function directRuleFor(category) {
  return DIRECT_CATEGORY_RULES.find((rule) => rule.match.includes(category));
}

function categoryAffinity(targetCategory, candidateCategory) {
  if (!targetCategory || !candidateCategory) {
    return { score: 0, reason: "нет категории" };
  }
  if (targetCategory === candidateCategory) {
    return { score: 88, reason: "та же категория" };
  }

  const direct = directRuleFor(targetCategory);
  if (direct?.recommend.includes(candidateCategory)) {
    return { score: 78, reason: direct.reason };
  }

  const targetGroup = groupForCategory(targetCategory);
  const candidateGroup = groupForCategory(candidateCategory);
  if (targetGroup && targetGroup === candidateGroup) {
    return { score: 64, reason: "смежная категория в одной группе" };
  }

  const targetToken = targetCategory.split(/\s+/)[0]?.toLowerCase();
  const candidateToken = candidateCategory.split(/\s+/)[0]?.toLowerCase();
  if (targetToken && targetToken === candidateToken) {
    return { score: 42, reason: "похожее название категории" };
  }

  return { score: 0, reason: "нет явной связки" };
}

function metricScore(candidate) {
  const stockScore = Math.min(22, Math.log10(candidate.fbo + 1) * 8);
  const ordersScore = Math.min(28, Math.log10(candidate.orders30d + 1) * 10);
  const planScore = candidate.planQty > 0 ? Math.min(14, Math.log10(candidate.planQty + 1) * 6) : 0;
  const contentScore = (candidate.hasRich ? 4 : 0) + (candidate.hasVideo ? 4 : 0);
  return stockScore + ordersScore + planScore + contentScore;
}

function enrichMetric(metric, cardsByArticle) {
  const card = cardsByArticle.get(metric.article);
  return {
    ...metric,
    productName: String(card?.imt_name || metric.productName || card?.slug || "-").trim(),
    category: String(card?.subj_name || metric.category || "-").trim(),
    brand: String(card?.selling?.brand_name || "").trim(),
    hasRecommendations: card?.has_seller_recommendations === true,
    hasRich: card?.has_rich === true,
    hasVideo: card?.media?.has_video === true,
    card,
  };
}

function chooseDiverseCandidates(scored, targetCategory) {
  const result = [];
  const perCategory = new Map();
  const usedArticles = new Set();

  const addItem = (item) => {
    if (!item || usedArticles.has(item.candidate.article)) return;
    result.push(item);
    usedArticles.add(item.candidate.article);
    perCategory.set(item.candidate.category, (perCategory.get(item.candidate.category) || 0) + 1);
  };

  for (const category of requiredCategoryNames(targetCategory)) {
    addItem(scored.find((item) => item.candidate.category === category));
  }

  for (const item of scored) {
    if (usedArticles.has(item.candidate.article)) continue;
    const used = perCategory.get(item.candidate.category) || 0;
    if (used >= 2 && result.length < 4) continue;
    addItem(item);
    if (result.length >= MAX_ARTICLES_PER_TARGET) break;
  }
  return result;
}

function requiredCategoryNames(targetCategory) {
  if (groupForCategory(targetCategory) !== "pool") return [];
  return ["Бассейны каркасные"];
}

function chooseRecommendedCategories(targetCategory, categoryScores) {
  const sorted = [...categoryScores.values()]
    .sort((a, b) => b.score - a.score || b.count - a.count || a.category.localeCompare(b.category, "ru"));
  const selected = [];
  const selectedNames = new Set();

  const addCategory = (item) => {
    if (!item || selectedNames.has(item.category)) return;
    selected.push(item);
    selectedNames.add(item.category);
  };

  for (const category of requiredCategoryNames(targetCategory)) {
    addCategory(categoryScores.get(category));
  }
  for (const item of sorted) {
    addCategory(item);
  }

  return selected;
}

function buildSuggestions({ targets, candidatesByCabinet }) {
  const suggestions = [];

  for (const target of targets) {
    const pool = candidatesByCabinet.get(target.cabinet) || [];
    const scored = [];

    for (const candidate of pool) {
      if (candidate.article === target.article) continue;
      if (candidate.fbo <= 10) continue;
      const affinity = categoryAffinity(target.category, candidate.category);
      if (affinity.score <= 0) continue;
      const score = affinity.score + metricScore(candidate);
      scored.push({ candidate, affinity, score });
    }

    scored.sort((a, b) => b.score - a.score || b.candidate.orders30d - a.candidate.orders30d || b.candidate.fbo - a.candidate.fbo);
    const picked = chooseDiverseCandidates(scored, target.category);

    const categoryScores = new Map();
    for (const item of scored) {
      const category = item.candidate.category;
      const current = categoryScores.get(category) || { category, score: 0, count: 0, reason: item.affinity.reason };
      current.score = Math.max(current.score, item.score);
      current.count += 1;
      categoryScores.set(category, current);
    }
    const recommendedCategories = chooseRecommendedCategories(target.category, categoryScores);

    suggestions.push({
      target,
      picked,
      recommendedCategories,
      candidatePoolSize: scored.length,
      candidateCategoryCount: categoryScores.size,
    });
  }

  return suggestions;
}

function recommendedCategoriesText(categories) {
  if (!categories.length) return "-";
  return categories.map((item) => valueOrDash(item.category)).join(", ");
}

function candidateArticlesText(items) {
  if (!items.length) return "-";
  return items
    .map(({ candidate }) => `${articleLink(candidate.article)} (${valueOrDash(candidate.category)}, FBO ${fmtInt(candidate.fbo)}, 30д ${fmtInt(candidate.orders30d)})`)
    .join("<br>");
}

function whyText(items) {
  if (!items.length) return "Нет релевантных товаров-кандидатов с FBO > 10 внутри того же ИП.";
  const reasons = [...new Set(items.map((item) => item.affinity.reason))].slice(0, 2);
  const top = items[0].candidate;
  const topBits = [`топ-кандидат FBO ${fmtInt(top.fbo)}`, `заказы 30д ${fmtInt(top.orders30d)}`];
  if (top.planQty > 0) topBits.push(`план ${fmtInt(top.planQty)}`);
  return `${reasons.join(", ")}; ${topBits.join(", ")}.`;
}

function whyWithPoolText(suggestion) {
  const base = whyText(suggestion.picked);
  const pool = `В релевантном пуле FBO > 10 внутри ИП: ${fmtInt(suggestion.candidatePoolSize)} артикулов, ${fmtInt(suggestion.candidateCategoryCount)} категорий.`;
  return `${base} ${pool}`;
}

function buildCategorySummary(suggestions) {
  const grouped = new Map();
  for (const suggestion of suggestions) {
    const groupKey = `${suggestion.target.cabinet}::${suggestion.target.category}`;
    const row = grouped.get(groupKey) || {
      cabinet: suggestion.target.cabinet,
      category: suggestion.target.category,
      count: 0,
      categoryCounts: new Map(),
    };
    row.count += 1;
    for (const category of suggestion.recommendedCategories) {
      row.categoryCounts.set(category.category, (row.categoryCounts.get(category.category) || 0) + 1);
    }
    grouped.set(groupKey, row);
  }

  return [...grouped.values()]
    .map((row) => ({
      ...row,
      recommended: [...row.categoryCounts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ru"))
        .map(([category]) => category),
    }))
    .sort((a, b) => a.cabinet.localeCompare(b.cabinet, "ru") || b.count - a.count || a.category.localeCompare(b.category, "ru"));
}

function buildJsonPayload({ suggestions, stockDate, planMonth, ordersFrom, ordersTo, totalCandidates }) {
  return {
    generatedAt: nowIso(),
    stockDate,
    planMonth,
    ordersFrom,
    ordersTo,
    totalCandidates,
    rows: suggestions.map((suggestion) => ({
      cabinet: suggestion.target.cabinet,
      article: suggestion.target.article,
      category: suggestion.target.category,
      productName: suggestion.target.productName,
      fbo: suggestion.target.fbo,
      planQty: suggestion.target.planQty,
      orders30d: suggestion.target.orders30d,
      candidatePoolSize: suggestion.candidatePoolSize,
      candidateCategoryCount: suggestion.candidateCategoryCount,
      recommendedCategories: suggestion.recommendedCategories.map((item) => ({
        category: item.category,
        count: item.count,
        reason: item.reason,
        score: Number(item.score.toFixed(2)),
      })),
      candidates: suggestion.picked.map((item) => ({
        article: item.candidate.article,
        category: item.candidate.category,
        productName: item.candidate.productName,
        fbo: item.candidate.fbo,
        planQty: item.candidate.planQty,
        orders30d: item.candidate.orders30d,
        reason: item.affinity.reason,
        score: Number(item.score.toFixed(2)),
      })),
      why: whyWithPoolText(suggestion),
    })),
  };
}

function buildMarkdown({ suggestions, stockDate, planMonth, ordersFrom, ordersTo, totalCandidates }) {
  const categorySummary = buildCategorySummary(suggestions);
  const generatedAt = formatMskDateTime(nowIso());
  const lines = [
    "# Настройки Рекомендаций Продавца",
    "",
    `> **Сформировано:** ${generatedAt}`,
    "",
    "| **Как использовать** |",
    "|---|",
    "| 1. В WB заполнять рекомендации товарами только из того же ИП.<br>2. Если конкретного артикула нет в интерфейсе WB, взять следующую категорию из блока «Категории для рекомендаций». |",
    "",
    `Всего товаров без рекомендаций в рабочем списке: ${suggestions.length}`,
    "",
    "## Категории для рекомендаций",
    "",
    "| ИП | Категория товара | Товаров без рекомендаций | Какие категории брать внутри ИП |",
    "|---|---|---:|---|",
    ...categorySummary.map((row) => [
      valueOrDash(row.cabinet),
      valueOrDash(row.category),
      fmtInt(row.count),
      valueOrDash(row.recommended.join(", ")),
    ]).map((cells) => `| ${cells.join(" | ")} |`),
    "",
    "## Детализация по артикулам",
    "",
    "| ИП | Артикул | Категория | Название | FBO | План | Заказы 30д | Рекомендуемые категории | Артикулы для рекомендаций | Почему |",
    "|---|---|---|---|---:|---:|---:|---|---|---|",
    ...suggestions.map((suggestion) => {
      const target = suggestion.target;
      const cells = [
        valueOrDash(target.cabinet),
        articleLink(target.article),
        valueOrDash(target.category),
        valueOrDash(target.productName),
        fmtInt(target.fbo),
        fmtInt(target.planQty),
        fmtInt(target.orders30d),
        recommendedCategoriesText(suggestion.recommendedCategories),
        candidateArticlesText(suggestion.picked),
        whyWithPoolText(suggestion),
      ];
      return `| ${cells.join(" | ")} |`;
    }),
    "",
    "## Методика",
    "",
    `**Рабочий список:** товары, где в открытом WB \`card.json\` \`has_seller_recommendations !== true\` и план продаж за ${planMonth.slice(0, 7)} > 10 или FBO > 10.`,
    "",
    `**Кандидаты:** товары из того же ИП с FBO > 10 на ${stockDate}; нерелевантные категории отрезаются логикой связок категорий.`,
    "",
    "**Вывод артикулов:** в строке показан топ-6 после ранжирования; расчет идет по всем релевантным артикулам с FBO > 10 внутри того же ИП.",
    "",
    `**Метрики продаж:** заказы и выручка за период ${ordersFrom} - ${ordersTo}.`,
    "",
    `**Ранжирование:** связка категорий + FBO + заказы 30д + план продаж + базовая контент-готовность кандидата.`,
    "",
    `**Пул кандидатов:** ${totalCandidates} товаров с FBO > 10 после привязки к ИП.`,
    "",
  ];
  return lines.join("\n");
}

function validateMarkdown(markdown, expectedRows) {
  const detailRows = markdown
    .split("\n")
    .filter((line) => /^\| (?!-)(?!ИП \|)(?:[^|]+\| \[\d+\])/.test(line));
  if (detailRows.length !== expectedRows) {
    throw new Error(`Expected ${expectedRows} detail rows, got ${detailRows.length}`);
  }
  const bad = detailRows.filter((line) => line.trim().slice(1, -1).split(/(?<!\\)\|/).length !== 10);
  if (bad.length) throw new Error(`Bad detail row width: ${bad[0]}`);
}

async function main() {
  const { stockDate, planMonth, ordersFrom, ordersTo, metrics } = await loadMetricsFromMysql();
  const workingArticles = [...new Set(metrics
    .filter((metric) => metric.planQty > 10 || metric.fbo > 10)
    .map((metric) => metric.article))];
  const cardsByArticle = await loadCardsByArticle(workingArticles);

  const metricByKey = new Map();
  for (const metric of metrics) {
    const enriched = enrichMetric(metric, cardsByArticle);
    metricByKey.set(key(enriched.cabinet, enriched.article), enriched);
  }

  const candidatesByCabinet = new Map();
  let totalCandidates = 0;
  for (const metric of metricByKey.values()) {
    if (metric.fbo <= 10 || !metric.category || !metric.productName) continue;
    if (!candidatesByCabinet.has(metric.cabinet)) candidatesByCabinet.set(metric.cabinet, []);
    candidatesByCabinet.get(metric.cabinet).push(metric);
    totalCandidates += 1;
  }

  for (const rows of candidatesByCabinet.values()) {
    rows.sort((a, b) => b.orders30d - a.orders30d || b.fbo - a.fbo || b.planQty - a.planQty);
  }

  const targets = [...metricByKey.values()]
    .filter((row) => !row.hasRecommendations && row.cabinet !== "-" && row.category && row.productName)
    .filter((row) => row.planQty > 10 || row.fbo > 10)
    .sort((a, b) =>
      a.cabinet.localeCompare(b.cabinet, "ru")
      || (b.fbo > 50 && b.planQty > 10 ? 1 : 0) - (a.fbo > 50 && a.planQty > 10 ? 1 : 0)
      || b.fbo - a.fbo
      || a.category.localeCompare(b.category, "ru")
      || Number(a.article) - Number(b.article),
    );

  const suggestions = buildSuggestions({ targets, candidatesByCabinet });
  const markdown = buildMarkdown({ suggestions, stockDate, planMonth, ordersFrom, ordersTo, totalCandidates });
  const jsonPayload = buildJsonPayload({ suggestions, stockDate, planMonth, ordersFrom, ordersTo, totalCandidates });
  validateMarkdown(markdown, suggestions.length);
  fs.writeFileSync(OUT_MD, markdown, "utf8");
  fs.writeFileSync(OUT_JSON, `${JSON.stringify(jsonPayload, null, 2)}\n`, "utf8");

  process.stdout.write(JSON.stringify({
    out: OUT_MD,
    json: OUT_JSON,
    targets: suggestions.length,
    totalCandidates,
    stockDate,
    planMonth,
    ordersFrom,
    ordersTo,
  }, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
