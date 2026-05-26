#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  XwayApiClient,
  autoRuleProblem,
  campaignBusinessType,
  campaignId,
  campaignLimitSummary,
  campaignPaymentType,
  isActiveOrPaused,
  isAutoRuleConfigured,
  isBudgetRuleConfigured,
  isSpendLimitConfigured,
  mapWithConcurrency,
  normalizeAutoRule,
  normalizeCampaignStatusCode,
  numberOrZero,
  summarizePauseIssues,
} from "../lib/xway-api.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_URL = "https://xway-bt4.pages.dev/drr-analytics";
const ANALYZER_URL = "https://mcp.mpvibe.ru/mcp/analyzer";
const MARKETERS_CSV_URL =
  "https://docs.google.com/spreadsheets/d/1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4/gviz/tq?tqx=out:csv&gid=1574673852";
const REPORT_TZ = "Europe/Moscow";
const FBO_THRESHOLD = 10;
const LIMIT_ACTIVITY_THRESHOLD_HOURS = 4;
const TYPE_ORDER = new Map([
  ["Единая ставка", 1],
  ["Ручная ставка: поиск", 2],
  ["Ручная ставка: рекомендации", 3],
  ["Ручная ставка: поиск + рекомендации", 4],
  ["Оплата за клики", 5],
]);

const OUT_LIMITS = path.join(ROOT, "1. Проблемы: настройка лимитов и бюджетов.md");
const OUT_ACTIVITY = path.join(ROOT, "2. Проблемы: вылеты лимитов.md");
const OUT_AUTO = path.join(ROOT, "3. Проблемы: Автоисключения Поиска.md");
const OUT_INSTRUCTION = path.join(ROOT, "Инструкция: отчеты по проблемам лимитов.md");

function isoDateInTimezone(date = new Date(), timeZone = REPORT_TZ) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function addDays(isoDate, amount) {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function resolvePeriod() {
  if (process.env.REPORT_START && process.env.REPORT_END) {
    return { start: process.env.REPORT_START, end: process.env.REPORT_END };
  }
  const todayMsk = isoDateInTimezone();
  const end = addDays(todayMsk, -1);
  const start = addDays(end, -2);
  return { start, end };
}

function nowIso() {
  return new Date().toISOString();
}

function formatMskDateTime(value = new Date()) {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: REPORT_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (inQuotes) {
      if (char === '"' && next === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        cell += char;
      }
      continue;
    }
    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell);
  rows.push(row);
  return rows.filter((item) => item.some((value) => String(value || "").trim()));
}

async function loadMarketers() {
  const response = await fetch(MARKETERS_CSV_URL);
  if (!response.ok) {
    throw new Error(`Failed to load marketers CSV: ${response.status}`);
  }
  const rows = parseCsv(await response.text());
  const marketers = new Map();
  for (const row of rows) {
    const article = String(row[1] || "").trim();
    const marketer = String(row[7] || "").trim();
    if (/^\d+$/.test(article) && marketer) {
      marketers.set(article, marketer);
    }
  }
  return marketers;
}

function readAnalyzerToken() {
  if (process.env.ABCAGE_ANALYZER_TOKEN) return process.env.ABCAGE_ANALYZER_TOKEN;
  const configPath = path.join(process.env.HOME || "", ".codex", "config.toml");
  const text = fs.existsSync(configPath) ? fs.readFileSync(configPath, "utf8") : "";
  const match = text.match(/ABCAGE_ANALYZER_TOKEN\s*=\s*"([^"]+)"/);
  if (!match) throw new Error("ABCAGE_ANALYZER_TOKEN not found");
  return match[1];
}

class McpSql {
  constructor() {
    this.proc = spawn("npx", ["-y", "mcp-remote", ANALYZER_URL, "--header", "Authorization: Bearer ${ABCAGE_ANALYZER_TOKEN}"], {
      env: { ...process.env, ABCAGE_ANALYZER_TOKEN: readAnalyzerToken() },
      stdio: ["pipe", "pipe", "ignore"],
    });
    this.nextId = 1;
    this.buffer = "";
    this.waiters = new Map();
    this.proc.stdout.setEncoding("utf8");
    this.proc.stdout.on("data", (chunk) => this.handleData(chunk));
  }

  handleData(chunk) {
    this.buffer += chunk;
    let newlineIndex;
    while ((newlineIndex = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, newlineIndex).trim();
      this.buffer = this.buffer.slice(newlineIndex + 1);
      if (!line.startsWith("{")) continue;
      let payload;
      try {
        payload = JSON.parse(line);
      } catch {
        continue;
      }
      const waiter = this.waiters.get(payload.id);
      if (waiter) {
        this.waiters.delete(payload.id);
        waiter.resolve(payload);
      }
    }
  }

  send(message) {
    this.proc.stdin.write(`${JSON.stringify(message)}\n`);
  }

  readId(id, timeoutMs = 120000) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.waiters.delete(id);
        reject(new Error(`MCP response timeout for id ${id}`));
      }, timeoutMs);
      this.waiters.set(id, {
        resolve: (payload) => {
          clearTimeout(timeout);
          resolve(payload);
        },
      });
    });
  }

  async init() {
    const id = this.nextId;
    this.nextId += 1;
    this.send({
      jsonrpc: "2.0",
      id,
      method: "initialize",
      params: {
        protocolVersion: "2024-11-05",
        capabilities: {},
        clientInfo: { name: "xway-limit-notifications", version: "1.0" },
      },
    });
    await this.readId(id);
    this.send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
  }

  async query(sql) {
    const id = this.nextId;
    this.nextId += 1;
    this.send({
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name: "sql__mysql_query", arguments: { sql } },
    });
    const response = await this.readId(id);
    const content = response?.result?.content?.[0]?.text || "";
    if (content.startsWith("Error:")) throw new Error(content);
    return JSON.parse(content);
  }

  close() {
    if (this.proc?.exitCode === null) {
      this.proc.kill("SIGTERM");
    }
  }
}

async function loadArticleDbInfo(articles) {
  const normalized = [...new Set(articles.map((article) => String(article || "").trim()).filter((article) => /^\d+$/.test(article)))];
  const result = new Map();
  if (!normalized.length) return result;

  const db = new McpSql();
  await db.init();
  try {
    for (let offset = 0; offset < normalized.length; offset += 400) {
      const chunk = normalized.slice(offset, offset + 400);
      const inList = chunk.map((article) => `'${article}'`).join(",");
      const rows = await db.query(`
        WITH
          latest_stock AS (
            SELECT MAX(date) AS stock_date
            FROM mp.mp_core__realtime_stocks_data
          ),
          cards AS (
            SELECT
              CAST(sku AS CHAR) AS sku,
              MAX(NULLIF(short_name, '')) AS short_name,
              MAX(NULLIF(name, '')) AS full_name,
              MAX(NULLIF(object, '')) AS category
            FROM mp.wb_core__card
            WHERE CAST(sku AS CHAR) IN (${inList})
            GROUP BY CAST(sku AS CHAR)
          ),
          stocks AS (
            SELECT
              CAST(sku AS CHAR) AS sku,
              SUM(COALESCE(fbo_real, 0)) AS fbo_current
            FROM mp.mp_core__realtime_stocks_data
            WHERE date = (SELECT stock_date FROM latest_stock)
              AND CAST(sku AS CHAR) IN (${inList})
            GROUP BY CAST(sku AS CHAR)
          )
        SELECT
          COALESCE(cards.sku, stocks.sku) AS sku,
          COALESCE(cards.short_name, cards.full_name, COALESCE(cards.sku, stocks.sku)) AS product_name,
          COALESCE(cards.category, '-') AS category,
          COALESCE(stocks.fbo_current, 0) AS fbo_current
        FROM cards
        LEFT JOIN stocks ON stocks.sku = cards.sku;
      `);
      for (const row of rows) {
        result.set(String(row.sku), {
          article: String(row.sku),
          productName: row.product_name || String(row.sku),
          category: row.category || "-",
          fbo: Math.trunc(Number(row.fbo_current || 0)),
        });
      }
    }
  } finally {
    db.close();
  }
  return result;
}

function initialCampaignSignal(product, statItem) {
  const campaignData = product?.campaigns_data || {};
  const states = Object.values(campaignData).filter((value) => value && typeof value === "object" && !Array.isArray(value));
  if (states.some((state) => ["ACTIVE", "PAUSED"].includes(normalizeCampaignStatusCode({ status: state.status })))) return true;
  return Number(statItem?.campaigns_count || 0) > 0 || Number(campaignData.manual_count || 0) > 0;
}

async function loadBaseProducts(client) {
  const shops = await client.listShops();
  const shopResults = await mapWithConcurrency(shops || [], 2, async (shop) => {
    const shopId = Number(shop?.id);
    if (!Number.isFinite(shopId)) return { rows: [], error: `invalid shop id: ${shop?.id}` };
    try {
      const listing = await client.shopListing(shopId);
      const statMap = listing.listStat?.products_wb || {};
      const rows = (listing.listWo?.products_wb || [])
        .map((product) => {
          const productId = Number(product?.id);
          const article = String(product?.external_id || "").trim();
          if (!article || !Number.isFinite(productId)) return null;
          const statItem = statMap[String(productId)] || {};
          return {
            article,
            shopId,
            shopName: shop?.name || `Кабинет ${shopId}`,
            productId,
            productUrl: `https://am.xway.ru/wb/shop/${shopId}/product/${productId}`,
            xwayName: product?.name_custom || product?.name || article,
            xwayCategory: product?.category_keyword || "-",
            xwayStock: Number(statItem?.stock || 0),
            expenseSum: Number(statItem?.stat?.sum || 0),
            campaignsCount: Number(statItem?.campaigns_count || 0),
            hasCampaignSignal: initialCampaignSignal(product, statItem),
          };
        })
        .filter(Boolean);
      return { rows, error: null };
    } catch (error) {
      return { rows: [], error: error instanceof Error ? error.message : String(error) };
    }
  });

  return {
    rows: shopResults.flatMap((item) => item.rows),
    errors: shopResults.filter((item) => item.error).map((item) => item.error),
  };
}

function articleInfo(item, dbInfo, marketers) {
  const info = dbInfo.get(item.article);
  return {
    ...item,
    productName: info?.productName || item.xwayName || item.article,
    category: info?.category || item.xwayCategory || "-",
    fbo: info?.fbo ?? 0,
    marketer: marketers.get(item.article) || "—",
  };
}

async function loadProductDetails(client, items) {
  let errors = 0;
  const rows = await mapWithConcurrency(items, Number(process.env.XWAY_STATA_CONCURRENCY || 2), async (item) => {
    try {
      const stata = await client.productStata(item.shopId, item.productId);
      const campaigns = (stata?.campaign_wb || []).filter(isActiveOrPaused);
      return { ...item, campaigns, stataError: null };
    } catch (error) {
      errors += 1;
      return { ...item, campaigns: [], stataError: error instanceof Error ? error.message : String(error) };
    }
  });
  return { rows, errors };
}

function mdEscape(value) {
  return String(value ?? "—")
    .replace(/\|/g, "\\|")
    .replace(/\r?\n/g, " ")
    .trim() || "—";
}

function mdCell(value) {
  return mdEscape(value || "—");
}

function fmtInt(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return Math.trunc(numeric).toLocaleString("ru-RU");
}

function fmtMoney(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${Math.round(numeric).toLocaleString("ru-RU")} ₽`;
}

function fmtHours(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const rounded = Math.round(numeric * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : String(rounded).replace(".", ",");
  return `${text} ч`;
}

function campaignTypeSortValue(label) {
  return TYPE_ORDER.get(label) || 99;
}

function buildLimitSetupRows(items) {
  const rows = [];
  for (const item of items) {
    for (const campaign of item.campaigns) {
      const missingSpendLimit = !isSpendLimitConfigured(campaign);
      const missingBudgetRule = !isBudgetRuleConfigured(campaign);
      if (!missingSpendLimit && !missingBudgetRule) continue;
      const summary = campaignLimitSummary(campaign);
      rows.push({
        ...item,
        campaignType: campaignBusinessType(campaign),
        missingSpendLimit,
        missingBudgetRule,
        issueCount: Number(missingSpendLimit) + Number(missingBudgetRule),
        spendLimit: summary.spend_limit,
        budgetLimit: summary.budget_limit,
      });
    }
  }
  return rows.sort((left, right) => {
    const issueDiff = right.issueCount - left.issueCount;
    if (issueDiff) return issueDiff;
    const spendDiff = right.expenseSum - left.expenseSum;
    if (spendDiff) return spendDiff;
    const articleDiff = left.article.localeCompare(right.article, "ru");
    if (articleDiff) return articleDiff;
    return campaignTypeSortValue(left.campaignType) - campaignTypeSortValue(right.campaignType);
  });
}

async function buildLimitActivityRows(client, items) {
  const startedAt = Date.now();
  let fallback120 = 0;
  let errors = 0;
  const rowMaps = await mapWithConcurrency(items, Number(process.env.XWAY_HISTORY_PRODUCT_CONCURRENCY || 2), async (item) => {
    const grouped = new Map();
    const campaignResults = await mapWithConcurrency(item.campaigns, Number(process.env.XWAY_HISTORY_CAMPAIGN_CONCURRENCY || 2), async (campaign) => {
      const id = campaignId(campaign);
      if (!id) return { campaign, id, error: "campaign id is missing", issues: null };
      try {
        let payload = await client.campaignStatusPauseHistory(item.shopId, item.productId, id, 60);
        if (payload?.next_page?.has_next) {
          fallback120 += 1;
          payload = await client.campaignStatusPauseHistory(item.shopId, item.productId, id, 120);
        }
        return { campaign, id, error: null, issues: summarizePauseIssues(payload, client.start, client.end) };
      } catch (error) {
        errors += 1;
        return { campaign, id, error: error instanceof Error ? error.message : String(error), issues: null };
      }
    });

    for (const result of campaignResults) {
      if (!result.issues) continue;
      const acceptedKinds = ["limit", "budget"].filter((kind) => result.issues[kind].maxIncidentHours >= LIMIT_ACTIVITY_THRESHOLD_HOURS);
      if (!acceptedKinds.length) continue;
      const type = campaignBusinessType(result.campaign);
      const current =
        grouped.get(type) || {
          ...item,
          campaignType: type,
          limitHours: 0,
          limitMaxHours: 0,
          limitIncidents: 0,
          budgetHours: 0,
          budgetMaxHours: 0,
          budgetIncidents: 0,
          totalHours: 0,
          maxIncidentHours: 0,
          totalIncidents: 0,
        };
      for (const kind of acceptedKinds) {
        const issue = result.issues[kind];
        if (kind === "limit") {
          current.limitHours += issue.hours;
          current.limitMaxHours = Math.max(current.limitMaxHours, issue.maxIncidentHours);
          current.limitIncidents += issue.incidents;
        } else {
          current.budgetHours += issue.hours;
          current.budgetMaxHours = Math.max(current.budgetMaxHours, issue.maxIncidentHours);
          current.budgetIncidents += issue.incidents;
        }
        current.totalHours += issue.hours;
        current.maxIncidentHours = Math.max(current.maxIncidentHours, issue.maxIncidentHours);
        current.totalIncidents += issue.incidents;
      }
      grouped.set(type, current);
    }
    return grouped;
  });

  const rows = rowMaps
    .flatMap((grouped) => [...grouped.values()])
    .sort((left, right) => {
      const maxDiff = right.maxIncidentHours - left.maxIncidentHours;
      if (maxDiff) return maxDiff;
      const totalDiff = right.totalHours - left.totalHours;
      if (totalDiff) return totalDiff;
      const fboDiff = right.fbo - left.fbo;
      if (fboDiff) return fboDiff;
      const articleDiff = left.article.localeCompare(right.article, "ru");
      if (articleDiff) return articleDiff;
      return campaignTypeSortValue(left.campaignType) - campaignTypeSortValue(right.campaignType);
    });

  return {
    rows,
    fallback120,
    errors,
    elapsedSeconds: (Date.now() - startedAt) / 1000,
  };
}

async function buildAutoExclusionRows(client, items) {
  const startedAt = Date.now();
  let cpcSkipped = 0;
  let configured = 0;
  let autoErrors = 0;
  let clusterErrors = 0;

  const itemRows = await mapWithConcurrency(items, Number(process.env.XWAY_AUTO_PRODUCT_CONCURRENCY || 2), async (item) => {
    const campaigns = item.campaigns.filter((campaign) => {
      if (campaignPaymentType(campaign) === "cpc") {
        cpcSkipped += 1;
        return false;
      }
      return normalizeCampaignStatusCode(campaign) !== "FROZEN";
    });
    const rows = await mapWithConcurrency(campaigns, Number(process.env.XWAY_AUTO_CAMPAIGN_CONCURRENCY || 2), async (campaign) => {
      const id = campaignId(campaign);
      if (!id) return null;
      let rule = null;
      let ruleError = null;
      try {
        rule = normalizeAutoRule(await client.campaignAutoExcludeRule(item.shopId, item.productId, id));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!/Unexpected end|404|not found|не существует|не найден/i.test(message)) {
          autoErrors += 1;
          ruleError = message;
        }
      }
      if (isAutoRuleConfigured(rule)) {
        configured += 1;
        return null;
      }

      let clustersWithSpend = 0;
      let fixedClusters = 0;
      try {
        const clusterPayload = await client.campaignNormqueryStats(item.shopId, item.productId, id);
        const normqueries = clusterPayload?.normqueries || [];
        clustersWithSpend = normqueries.filter((cluster) => numberOrZero(cluster?.expense) > 0 && cluster?.excluded !== true).length;
        fixedClusters = normqueries.filter((cluster) => cluster?.fixed === true).length;
      } catch {
        clusterErrors += 1;
      }

      const spend = numberOrZero(campaign?.stat?.sum);
      if (spend <= 0) return null;
      const type = campaignBusinessType(campaign);
      if (type === "Единая ставка" && clustersWithSpend <= 0) return null;
      const problem = autoRuleProblem(rule, ruleError);
      return {
        ...item,
        campaignType: type,
        problem: problem.problem,
        ruleText: problem.rule,
        clustersWithSpend,
        fixedClusters,
        spend,
        orders: numberOrZero(campaign?.stat?.orders),
      };
    });
    return rows.filter(Boolean);
  });

  const rows = itemRows
    .flat()
    .sort((left, right) => {
      const configuredDiff = String(left.problem).localeCompare(String(right.problem), "ru");
      if (configuredDiff) return configuredDiff;
      const spendDiff = right.spend - left.spend;
      if (spendDiff) return spendDiff;
      const fboDiff = right.fbo - left.fbo;
      if (fboDiff) return fboDiff;
      return left.article.localeCompare(right.article, "ru");
    });

  return {
    rows,
    configured,
    cpcSkipped,
    autoErrors,
    clusterErrors,
    elapsedSeconds: (Date.now() - startedAt) / 1000,
  };
}

function baseTableCells(row) {
  return [
    row.article,
    `[XWAY](${row.productUrl})`,
    mdCell(row.productName),
    mdCell(row.category),
    mdCell(row.marketer),
    fmtInt(row.fbo),
    mdCell(row.campaignType),
  ];
}

function markdownTable(headers, rows) {
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.join(" | ")} |`),
  ].join("\n");
}

function markdownNote(lines) {
  return [
    "> **Примечание:**",
    ...lines.map((line) => `> • ${line}`),
  ].join("\n");
}

function buildLimitSetupMarkdown(rows, meta) {
  const tableRows = rows.map((row) => [
    ...baseTableCells(row),
    row.missingSpendLimit ? "не установлен" : "—",
    row.missingBudgetRule ? "не настроено" : "—",
  ]);
  return [
    "# Проблемы: настройка лимитов и бюджетов",
    "",
    `Период: ${meta.start} - ${meta.end}`,
    `Источник: ${SOURCE_URL}`,
    "",
    markdownTable(
      ["Артикул", "XWAY", "Название товара", "Категория", "Маркетолог", "Остаток FBO", "Тип РК", "Проблема лимит расхода", "Проблема пополнение бюджета"],
      tableRows,
    ),
    "",
    markdownNote([
      `Строк с проблемами: ${rows.length}`,
      `Условие: Остаток FBO из БД > ${FBO_THRESHOLD}`,
      `Товаров с РК/сигналом РК в XWAY до фильтра FBO: ${meta.initialCandidates}`,
      `Проверено после фильтра БД FBO > ${FBO_THRESHOLD}: ${meta.checkedProducts}`,
    ]),
    "",
  ].join("\n");
}

function buildActivityMarkdown(rows, meta) {
  const tableRows = rows.map((row) => [
    ...baseTableCells(row),
    row.limitIncidents ? "лимит расходов" : "—",
    row.limitIncidents ? fmtInt(row.limitIncidents) : "—",
    row.budgetIncidents ? "нехватка бюджета" : "—",
    row.budgetIncidents ? fmtInt(row.budgetIncidents) : "—",
    fmtHours(row.maxIncidentHours),
    fmtHours(row.totalHours),
    fmtInt(row.totalIncidents),
  ]);
  return [
    "# Проблемы: вылеты лимитов",
    "",
    `Период: ${meta.start} - ${meta.end}`,
    `Источник: ${SOURCE_URL}`,
    "",
    markdownTable(
      [
        "Артикул",
        "XWAY",
        "Название товара",
        "Категория",
        "Маркетолог",
        "Остаток FBO",
        "Тип РК",
        "Проблема лимит расхода",
        "Инциденты лимит расхода",
        "Проблема пополнение бюджета",
        "Инциденты пополнение бюджета",
        "Макс. неактивность подряд",
        "Всего неактивность",
        "Инциденты всего",
      ],
      tableRows,
    ),
    "",
    markdownNote([
      `Строк с вылетами: ${rows.length}`,
      `Условие: Остаток FBO из БД > ${FBO_THRESHOLD}`,
      `Порог вылета: статус «лимит расходов» или «нехватка бюджета» подряд не меньше ${LIMIT_ACTIVITY_THRESHOLD_HOURS} ч`,
      "Метод истории статусов: status-pause-history limit=60, fallback до 120 при полной странице",
      `Fallback до 120: ${meta.fallback120}`,
      `Товаров с РК/сигналом РК в XWAY до фильтра FBO: ${meta.initialCandidates}`,
      `Проверено после фильтра БД FBO > ${FBO_THRESHOLD}: ${meta.checkedProducts}`,
      `Ошибок догрузки истории статусов: ${meta.errors}`,
      `Время полного цикла сборки: ${String(Math.round(meta.elapsedSeconds * 10) / 10).replace(".", ",")} сек`,
    ]),
    "",
  ].join("\n");
}

function buildAutoMarkdown(rows, meta) {
  const tableRows = rows.map((row) => [
    ...baseTableCells(row),
    mdCell(row.problem),
    mdCell(row.ruleText),
    fmtInt(row.clustersWithSpend),
    fmtInt(row.fixedClusters),
    fmtMoney(row.spend),
    fmtInt(row.orders),
  ]);
  return [
    "# Проблемы: Автоисключения Поиска",
    "",
    `Период: ${meta.start} - ${meta.end}`,
    `Источник: ${SOURCE_URL}`,
    "",
    markdownTable(
      [
        "Артикул",
        "XWAY",
        "Название товара",
        "Категория",
        "Маркетолог",
        "Остаток FBO",
        "Тип РК",
        "Проблема автоисключения поиска",
        "Правило автоисключения",
        "Кластеры с тратами за 3 дня",
        "Зафиксированные кластеры",
        "Расход за период",
        "Заказы всего",
      ],
      tableRows,
    ),
    "",
    markdownNote([
      `Строк с проблемами: ${rows.length}`,
      `Условие: Остаток FBO из БД > ${FBO_THRESHOLD}`,
      "Стартовый фильтр: только CPM РК ACTIVE/PAUSED; FROZEN и CPC исключаются до проверки деталей",
      "Фильтр строк: Расход за период > 0; для Единой ставки Кластеры с тратами за 3 дня > 0",
      "Кластеры с тратами: normquery expense > 0 и excluded != true за период отчета",
      "Зафиксированные кластеры: normquery fixed = true",
      `Товаров с РК/сигналом РК в XWAY до фильтра FBO: ${meta.initialCandidates}`,
      `Проверено после фильтра БД FBO > ${FBO_THRESHOLD}: ${meta.checkedProducts}`,
      `CPC пропущено в смешанных товарах: ${meta.cpcSkipped}`,
      `Настроено РК: ${meta.configured}`,
      `Ошибок догрузки автоисключений: ${meta.autoErrors}`,
      `Ошибок догрузки кластеров: ${meta.clusterErrors}`,
      `Время полного цикла сборки: ${String(Math.round(meta.elapsedSeconds * 10) / 10).replace(".", ",")} сек`,
    ]),
    "",
  ].join("\n");
}

function countByMarketer(rows) {
  const counts = new Map();
  for (const row of rows) {
    counts.set(row.marketer, (counts.get(row.marketer) || 0) + 1);
  }
  return counts;
}

function marketerTitle(marketer) {
  return marketer === "—" ? "Без маркетолога" : marketer;
}

function buildPachcaMessage({ period, limitsRows, activityRows, autoRows }) {
  const byReport = {
    "Настройка лимитов и бюджетов": countByMarketer(limitsRows),
    "Вылеты лимитов": countByMarketer(activityRows),
    "Автоисключения поиска": countByMarketer(autoRows),
  };
  const marketers = [
    ...new Set(Object.values(byReport).flatMap((map) => [...map.keys()])),
  ].sort((left, right) => {
    if (left === "—") return 1;
    if (right === "—") return -1;
    return left.localeCompare(right, "ru");
  });

  const lines = [
    "**Проблемы биддера XWAY**",
    "",
    `_Отчет: ${process.env.REPORT_RUN_LABEL || "ручной запуск"}_`,
    `_Период: ${period.start} - ${period.end}_`,
    `_Сформировано: ${formatMskDateTime()} МСК_`,
    `_Фильтр: FBO-остаток из БД Акинатора > ${FBO_THRESHOLD}; XWAY CPM РК в ACTIVE/PAUSED._`,
    "",
    "**Сводка по маркетологам / отчетам / ошибкам:**",
  ];

  if (!marketers.length) {
    lines.push("• Проблем не найдено.");
  } else {
    for (const marketer of marketers) {
      lines.push(`**${marketerTitle(marketer)}**`);
      for (const [label, counts] of Object.entries(byReport)) {
        const count = counts.get(marketer) || 0;
        if (count) {
          lines.push(`• ${label}: **${count}**`);
        }
      }
      lines.push("");
    }
  }

  return lines.join("\n").trim();
}

function buildPachcaThreadMessage() {
  return [
    "**Описание файлов:**",
    `• \`${path.basename(OUT_LIMITS)}\`: артикулы с РК, где не установлен лимит расхода или не настроено правило пополнения бюджета.`,
    `• \`${path.basename(OUT_ACTIVITY)}\`: артикулы с вылетами по лимиту расходов или нехватке бюджета за период отчета.`,
    `• \`${path.basename(OUT_AUTO)}\`: РК с расходом, где не настроены автоисключения поиска; кластеры и расходы добавлены для проверки.`,
    `• \`${path.basename(OUT_INSTRUCTION)}\`: правила чтения отчетов, проверки строк и дальнейшие действия.`,
  ].join("\n");
}

function writeJson(filePath, payload) {
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

export async function buildReports() {
  const period = resolvePeriod();
  const client = new XwayApiClient(process.env, period);
  const [marketers, base] = await Promise.all([loadMarketers(), loadBaseProducts(client)]);
  const signalProducts = base.rows.filter((item) => item.hasCampaignSignal);
  const dbInfo = await loadArticleDbInfo(signalProducts.map((item) => item.article));
  const enriched = signalProducts
    .map((item) => articleInfo(item, dbInfo, marketers))
    .filter((item) => item.fbo > FBO_THRESHOLD);
  const details = await loadProductDetails(client, enriched);
  const checkedProducts = details.rows.filter((item) => item.campaigns.length);

  const commonMeta = {
    ...period,
    initialCandidates: signalProducts.length,
    checkedProducts: checkedProducts.length,
  };

  const limitsRows = buildLimitSetupRows(checkedProducts);
  const activity = await buildLimitActivityRows(client, checkedProducts);
  const auto = await buildAutoExclusionRows(client, checkedProducts);

  fs.writeFileSync(OUT_LIMITS, buildLimitSetupMarkdown(limitsRows, commonMeta), "utf8");
  fs.writeFileSync(OUT_ACTIVITY, buildActivityMarkdown(activity.rows, { ...commonMeta, ...activity }), "utf8");
  fs.writeFileSync(OUT_AUTO, buildAutoMarkdown(auto.rows, { ...commonMeta, ...auto }), "utf8");

  const manifest = {
    generatedAt: nowIso(),
    period,
    source: SOURCE_URL,
    files: {
      limits: OUT_LIMITS,
      activity: OUT_ACTIVITY,
      autoExclusions: OUT_AUTO,
      instruction: OUT_INSTRUCTION,
    },
    pachcaMessage: buildPachcaMessage({
      period,
      limitsRows,
      activityRows: activity.rows,
      autoRows: auto.rows,
    }),
    pachcaThreadMessage: buildPachcaThreadMessage(),
    stats: {
      totalXwayProducts: base.rows.length,
      xwayListingErrors: base.errors.length,
      initialCandidates: signalProducts.length,
      dbFboFilteredProducts: enriched.length,
      checkedProducts: checkedProducts.length,
      productStataErrors: details.errors,
      limitsRows: limitsRows.length,
      activityRows: activity.rows.length,
      autoRows: auto.rows.length,
      activityFallback120: activity.fallback120,
      activityErrors: activity.errors,
      autoConfigured: auto.configured,
      autoCpcSkipped: auto.cpcSkipped,
      autoErrors: auto.autoErrors,
      clusterErrors: auto.clusterErrors,
    },
  };

  const manifestPath = path.join(ROOT, `xway_limit_reports_${period.end}.json`);
  writeJson(manifestPath, manifest);
  return { ...manifest, manifestPath };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  buildReports()
    .then((manifest) => {
      console.log(JSON.stringify({ ok: true, manifest: manifest.manifestPath, stats: manifest.stats }, null, 2));
    })
    .catch((error) => {
      console.error(error);
      process.exit(1);
    });
}
