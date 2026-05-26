import fs from "node:fs";

const XWAY_BASE_ORIGIN = "https://am.xway.ru";
const RETRYABLE_STATUSES = new Set([429, 502, 503, 504]);

export function mapWithConcurrency(items, concurrency, mapper) {
  const limit = Math.max(1, Math.min(concurrency, items.length || 1));
  const results = new Array(items.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await mapper(items[currentIndex], currentIndex);
    }
  }

  return Promise.all(Array.from({ length: limit }, () => worker())).then(() => results);
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function decodeBase64(value) {
  if (!value) return "";
  return Buffer.from(value, "base64").toString("utf8");
}

function readStorageState(env) {
  const rawJson = String(env.XWAY_STORAGE_STATE_JSON || "").trim();
  const rawBase64 = String(env.XWAY_STORAGE_STATE_BASE64 || "").trim();
  const storagePath = String(env.XWAY_STORAGE_STATE_PATH || "").trim();
  const localPath = "/Users/looqich/Documents/XWAY/xway_storage_state.json";
  const raw =
    rawJson ||
    (rawBase64 ? decodeBase64(rawBase64) : "") ||
    (storagePath && fs.existsSync(storagePath) ? fs.readFileSync(storagePath, "utf8") : "") ||
    (fs.existsSync(localPath) ? fs.readFileSync(localPath, "utf8") : "");

  if (raw) {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.cookies)) {
      throw new Error("XWAY storage state must contain a cookies array.");
    }
    return parsed;
  }

  const cookieHeader = String(env.XWAY_COOKIE_HEADER || "").trim();
  if (cookieHeader) {
    return {
      cookies: cookieHeader
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean)
        .map((part) => {
          const separatorIndex = part.indexOf("=");
          if (separatorIndex <= 0) return null;
          return {
            name: part.slice(0, separatorIndex).trim(),
            value: part.slice(separatorIndex + 1).trim(),
          };
        })
        .filter((cookie) => cookie?.name && cookie?.value),
    };
  }

  const sessionId = String(env.XWAY_SESSIONID || "").trim();
  if (sessionId) {
    const cookies = [{ name: "sessionid", value: sessionId }];
    const csrfToken = String(env.XWAY_CSRF_TOKEN || env.XWAY_CSRFTOKEN || "").trim();
    if (csrfToken) cookies.push({ name: "csrftoken_v2", value: csrfToken });
    return { cookies };
  }

  throw new Error("XWAY auth is missing. Set XWAY_STORAGE_STATE_JSON, XWAY_STORAGE_STATE_BASE64, XWAY_COOKIE_HEADER, or XWAY_SESSIONID.");
}

function cookieHeaderFromStorage(storageState) {
  return (storageState.cookies || [])
    .filter((cookie) => cookie?.name && cookie?.value)
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
}

function csrfTokenFromStorage(storageState) {
  return (
    (storageState.cookies || []).find((cookie) => cookie?.name === "csrftoken_v2")?.value ||
    (storageState.cookies || []).find((cookie) => cookie?.name === "csrftoken")?.value ||
    ""
  );
}

function normalizeXwayErrorText(status, text, statusText) {
  const rawText = String(text || statusText || "").replace(/\s+/g, " ").trim();
  if (status === 503 || /temporarily unavailable|503 Service Temporarily Unavailable/i.test(rawText)) {
    return "XWAY temporarily unavailable (503).";
  }
  return rawText || `HTTP ${status}`;
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function numberOrZero(value) {
  const numeric = toNumber(value);
  return numeric === null ? 0 : numeric;
}

export class XwayApiClient {
  constructor(env, { start, end }) {
    this.env = env;
    this.start = start;
    this.end = end;
    this.storageState = readStorageState(env);
    this.cookieHeader = cookieHeaderFromStorage(this.storageState);
    this.csrfToken = String(env.XWAY_CSRF_TOKEN || env.XWAY_CSRFTOKEN || "").trim() || csrfTokenFromStorage(this.storageState);
  }

  headers({ referer = null, csrf = false, extraHeaders = {} } = {}) {
    const headers = new Headers({
      accept: "application/json, text/plain, */*",
      cookie: this.cookieHeader,
      ...extraHeaders,
    });
    if (referer) headers.set("referer", referer);
    if (csrf && this.csrfToken) {
      headers.set("x-csrftoken", this.csrfToken);
      headers.set("x-requested-with", "XMLHttpRequest");
    }
    return headers;
  }

  productUrl(shopId, productId) {
    return `${XWAY_BASE_ORIGIN}/wb/shop/${shopId}/product/${productId}`;
  }

  campaignUrl(shopId, productId, campaignId) {
    return `${this.productUrl(shopId, productId)}/campaign/${campaignId}/new-flow?stat=${this.start}..${this.end}`;
  }

  async requestJson(pathname, { method = "GET", referer = null, params = null, csrf = false, json = null } = {}) {
    const url = new URL(pathname, XWAY_BASE_ORIGIN);
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }

    const headers = this.headers({ referer, csrf });
    let body;
    if (json !== null && json !== undefined) {
      headers.set("content-type", "application/json; charset=utf-8");
      body = JSON.stringify(json);
    }

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const response = await fetch(url, {
        method,
        headers,
        body: method.toUpperCase() === "GET" ? undefined : body,
        redirect: "follow",
      });
      if (!response.ok) {
        const text = await response.text();
        if (RETRYABLE_STATUSES.has(response.status) && attempt < 2) {
          await wait(900 * (attempt + 1));
          continue;
        }
        throw new Error(`XWAY request failed (${response.status}): ${normalizeXwayErrorText(response.status, text, response.statusText)}`);
      }
      if (response.status === 204) return null;
      return response.json();
    }

    throw new Error("XWAY request failed: retry attempts exhausted");
  }

  listShops() {
    return this.requestJson("/api/adv/shop/list", { params: { query: "" } });
  }

  async shopListing(shopId) {
    const referer = `${XWAY_BASE_ORIGIN}/wb/shop/${shopId}`;
    const params = { start: this.start, end: this.end, is_active: 1, enabled: 1 };
    const [listWoResult, listStatResult] = await Promise.allSettled([
      this.requestJson(`/api/adv/shop/${shopId}/product/list-wo-stat`, { referer, params }),
      this.requestJson(`/api/adv/shop/${shopId}/product/list-stat`, { referer, params }),
    ]);
    if (listWoResult.status === "rejected" && listStatResult.status === "rejected") {
      throw new Error(`Failed to load XWAY listing for shop ${shopId}`);
    }
    return {
      listWo: listWoResult.status === "fulfilled" ? listWoResult.value : { products_wb: [] },
      listStat: listStatResult.status === "fulfilled" ? listStatResult.value : { products_wb: {} },
    };
  }

  productStata(shopId, productId) {
    return this.requestJson(`/api/adv/shop/${shopId}/product/${productId}/stata`, {
      referer: this.productUrl(shopId, productId),
      params: {
        is_active: 0,
        start: this.start,
        end: this.end,
        tags: "",
        active_camps: 1,
      },
    });
  }

  campaignStatusPauseHistory(shopId, productId, campaignId, limit = 60) {
    return this.requestJson(`/api/adv/shop/${shopId}/product/${productId}/campaign/${campaignId}/status-pause-history`, {
      method: "POST",
      referer: this.productUrl(shopId, productId),
      csrf: true,
      json: { limit },
    });
  }

  campaignAutoExcludeRule(shopId, productId, campaignId) {
    return this.requestJson(`/api/adv/shop/${shopId}/product/${productId}/campaign/${campaignId}/retrieve-ac-exclude-rule`, {
      referer: this.campaignUrl(shopId, productId, campaignId),
    });
  }

  campaignNormqueryStats(shopId, productId, campaignId) {
    const forJamEnd = new Date(`${this.end}T00:00:00Z`);
    const forJamStart = new Date(forJamEnd);
    forJamStart.setUTCDate(forJamStart.getUTCDate() - 30);
    return this.requestJson(`/api/adv/shop/${shopId}/product/${productId}/campaign/${campaignId}/normquery-stats`, {
      referer: this.campaignUrl(shopId, productId, campaignId),
      params: {
        search_mode: "cluster",
        search_part: "cluster",
        excludes: "",
        includes: "",
        exact_match: 0,
        start: this.start,
        end: this.end,
        dynamics_start: this.start,
        dynamics_end: this.end,
        for_jam_start: forJamStart.toISOString().slice(0, 10),
        for_jam_end: this.end,
        with_stats_only: 1,
        init: 1,
      },
    });
  }
}

function splitPauseReasonTokens(value) {
  if (Array.isArray(value)) return value.flatMap(splitPauseReasonTokens);
  if (value && typeof value === "object") {
    return [
      ...splitPauseReasonTokens(value.pause_reasons),
      ...splitPauseReasonTokens(value.paused_limiter),
      ...splitPauseReasonTokens(value.reason),
      ...splitPauseReasonTokens(value.status),
    ];
  }
  return String(value || "")
    .split(/[;,\s/]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

export function normalizeCampaignStatusCode(campaign) {
  const raw = campaign?.status_xway ?? campaign?.status ?? null;
  const normalized = String(raw || "").trim().toUpperCase();
  let statusCode = normalized || null;
  if (["ACTIVE", "АКТИВНА", "АКТИВЕН", "АКТИВНАЯ", "АКТИВНЫЙ"].includes(normalized)) statusCode = "ACTIVE";
  if (["PAUSED", "PAUSE", "ПАУЗА", "ПРИОСТАНОВЛЕНА", "ПРИОСТАНОВЛЕН", "ОСТАНОВЛЕНА", "ОСТАНОВЛЕН"].includes(normalized)) statusCode = "PAUSED";
  if (["FROZEN", "FREEZE", "ЗАМОРОЖЕНА", "ЗАМОРОЖЕН", "ЗАМОРОЗКА"].includes(normalized)) statusCode = "FROZEN";

  const statusText = [campaign?.status_xway, campaign?.status, campaign?.freeze_status].map((value) => String(value || "").toLowerCase()).join(" ");
  const pausePayload = campaign?.pause_reasons || {};
  const pauseTokens = splitPauseReasonTokens(pausePayload);
  const pausedUser = pausePayload?.paused_user ?? campaign?.paused_user ?? null;
  if (
    campaign?.is_freeze ||
    campaign?.is_frozen ||
    campaign?.frozen ||
    campaign?.freeze ||
    /заморож|freeze|frozen/.test(statusText) ||
    (statusCode === "PAUSED" && (pausedUser || pauseTokens.some((token) => ["user", "manual", "freeze", "frozen"].includes(token) || /замороз/.test(token))))
  ) {
    return "FROZEN";
  }
  return statusCode;
}

export function isActiveOrPaused(campaign) {
  const status = normalizeCampaignStatusCode(campaign);
  return status === "ACTIVE" || status === "PAUSED";
}

export function campaignPaymentType(campaign) {
  const source = [campaign?.payment_type, campaign?.name, campaign?.auction_mode, campaign?.auto_type]
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
  if (/cpc|click|клик|оплата\s+за\s+клики/.test(source)) return "cpc";
  return "cpm";
}

export function campaignBusinessType(campaign) {
  if (campaignPaymentType(campaign) === "cpc") return "Оплата за клики";
  if (campaign?.unified) return "Единая ставка";

  const auctionMode = String(campaign?.auction_mode || "").trim().toLowerCase();
  const autoType = String(campaign?.auto_type || "").trim().toLowerCase();
  const name = String(campaign?.name || "").trim().toLowerCase();
  const source = `${auctionMode} ${autoType} ${name}`;
  const searchSignal = toNumber(campaign?.min_cpm) !== null || toNumber(campaign?.mp_bid) !== null;
  const recomSignal = toNumber(campaign?.min_cpm_recom) !== null || toNumber(campaign?.mp_recom_bid) !== null;

  let hasSearch = false;
  let hasRecom = false;
  if (/search[_\s-]*recom|recom[_\s-]*search|searchrecom|поиск.*реком|реком.*поиск/.test(source)) {
    hasSearch = true;
    hasRecom = true;
  } else {
    hasSearch = searchSignal || /search|поиск/.test(source);
    hasRecom = recomSignal || /recom|recommend|реком/.test(source);
  }

  if (hasSearch && hasRecom) return "Ручная ставка: поиск + рекомендации";
  if (hasRecom) return "Ручная ставка: рекомендации";
  return "Ручная ставка: поиск";
}

function firstNumber(...values) {
  for (const value of values) {
    const numeric = toNumber(value);
    if (numeric !== null) return numeric;
  }
  return null;
}

function readSpendLimit(campaign) {
  const limitsByPeriod = campaign?.limits_by_period || {};
  const spendByPeriod = campaign?.spend || {};
  const items = Object.entries(limitsByPeriod).map(([period, config]) => ({
    period,
    active: Boolean(config?.active),
    limit: firstNumber(config?.limit, config?.limit_sum, config?.value, config?.sum),
    spent: firstNumber(spendByPeriod?.[period], spendByPeriod?.[String(period).toUpperCase()], spendByPeriod?.[String(period).toLowerCase()]),
  }));
  const directLimit = firstNumber(campaign?.spend_limit, campaign?.day_limit, campaign?.daily_limit, campaign?.limit, campaign?.limit_sum);
  if (directLimit !== null || campaign?.spend_limit_active) {
    items.push({
      period: campaign?.spend_limit_period ?? campaign?.limit_period ?? "DAY",
      active: Boolean(campaign?.spend_limit_active ?? campaign?.active),
      limit: directLimit,
      spent: firstNumber(campaign?.spend_limit_spent, campaign?.spent_today, campaign?.spend_day),
    });
  }
  return items.find((item) => item.active && String(item.period || "").toLowerCase().includes("day")) || items.find((item) => item.active) || items[0] || null;
}

export function campaignLimitSummary(campaign) {
  const spendLimit = readSpendLimit(campaign);
  const budgetRule = campaign?.budget_rule_config || campaign?.budget_rule || {};
  const budgetLimit = firstNumber(
    budgetRule.limit,
    budgetRule.limit_sum,
    budgetRule.value,
    campaign?.budget_limit,
    campaign?.budget_rule_limit,
  );

  return {
    spend_limit_active: Boolean(spendLimit?.active ?? campaign?.spend_limit_active),
    spend_limit: firstNumber(spendLimit?.limit),
    spend_spent_today: firstNumber(spendLimit?.spent),
    budget_rule_active: Boolean(budgetRule.active ?? campaign?.budget_rule_active),
    budget_limit: budgetLimit,
    budget_spent_today: firstNumber(budgetRule.spent, budgetRule.spent_today, budgetRule.current, budgetRule.used),
  };
}

export function isSpendLimitConfigured(campaign) {
  const summary = campaignLimitSummary(campaign);
  return Boolean(summary.spend_limit_active) && numberOrZero(summary.spend_limit) > 0;
}

export function isBudgetRuleConfigured(campaign) {
  const summary = campaignLimitSummary(campaign);
  return Boolean(summary.budget_rule_active) && numberOrZero(summary.budget_limit) > 0;
}

function boolOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  const normalized = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "on", "да"].includes(normalized)) return true;
  if (["false", "0", "no", "off", "нет"].includes(normalized)) return false;
  return null;
}

export function normalizeAutoRule(source) {
  const payload = source?.result && typeof source.result === "object" ? source.result : source;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  return {
    active: boolOrNull(payload.active),
    fixed: boolOrNull(payload.fixed),
    boost: toNumber(payload.boost),
    efficiency: toNumber(payload.efficiency),
    popularity: toNumber(payload.popularity),
    popularity_above: toNumber(payload.popularity_above ?? payload.popularityAbove),
    ctr: toNumber(payload.ctr),
    cpc: toNumber(payload.cpc),
    queries_to_exclude: Array.isArray(payload.queries_to_exclude) ? payload.queries_to_exclude : [],
  };
}

export function isAutoRuleConfigured(rule) {
  if (!rule || rule.active !== true) return false;
  if (rule.fixed === false) return true;
  return (
    rule.boost !== null ||
    rule.efficiency !== null ||
    rule.popularity !== null ||
    rule.popularity_above !== null ||
    rule.ctr !== null ||
    rule.cpc !== null ||
    Boolean(rule.queries_to_exclude?.length)
  );
}

export function autoRuleProblem(rule, error = null) {
  if (error) return { problem: "выключено", rule: "ошибка чтения правила" };
  if (!rule) return { problem: "выключено", rule: "правило не найдено" };
  if (rule.active === false) return { problem: "выключено", rule: "правило выключено" };
  if (rule.fixed === true && !isAutoRuleConfigured(rule)) return { problem: "нет условий", rule: "нет условий" };
  return { problem: "не настроено", rule: "правило не настроено" };
}

export function campaignId(campaign) {
  const value = campaign?.id ?? campaign?.campaign_id ?? campaign?.external_id ?? campaign?.wb_id;
  const numeric = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(numeric) ? numeric : null;
}

function parseRuDateTime(value, fallbackDate = null) {
  const text = String(value || "").trim();
  if (!text) return null;
  const dateMatch = text.match(/(\d{1,2})[.-](\d{1,2})(?:[.-](\d{4}))?/);
  const timeMatch = text.match(/(\d{1,2}):(\d{2})/);
  let year = fallbackDate?.getUTCFullYear() || new Date().getUTCFullYear();
  let month = fallbackDate ? fallbackDate.getUTCMonth() + 1 : null;
  let day = fallbackDate?.getUTCDate() || null;

  if (dateMatch) {
    day = Number.parseInt(dateMatch[1], 10);
    month = Number.parseInt(dateMatch[2], 10);
    if (dateMatch[3]) year = Number.parseInt(dateMatch[3], 10);
  }
  if (!day || !month || !year) return null;

  const hours = timeMatch ? Number.parseInt(timeMatch[1], 10) : 0;
  const minutes = timeMatch ? Number.parseInt(timeMatch[2], 10) : 0;
  const parsed = new Date(Date.UTC(year, month - 1, day, hours, minutes, 0, 0));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normalizePauseIntervals(payload) {
  return (payload?.tooltips || [])
    .map((item) => {
      const startAt = parseRuDateTime(item?.startDate);
      let endAt = item?.endDate ? parseRuDateTime(item.endDate, startAt) : new Date();
      if (startAt && endAt && endAt.getTime() <= startAt.getTime() && !/\d{1,2}[.-]\d{1,2}/.test(String(item?.endDate || ""))) {
        endAt = new Date(endAt.getTime() + 86400000);
      }
      return {
        startAt,
        endAt,
        status: item?.status,
        is_freeze: Boolean(item?.isFreeze),
        pause_reasons: item?.pauseReasons || [],
        paused_limiter: item?.pausedLimiter,
        paused_user: item?.pausedUser,
      };
    })
    .filter((item) => item.startAt && item.endAt);
}

function pauseIssueKinds(interval) {
  if (interval.is_freeze) return [];
  const statusText = String(interval.status || "").toLowerCase();
  if (/актив|active/.test(statusText)) return [];
  const joined = [...splitPauseReasonTokens(interval.pause_reasons), ...splitPauseReasonTokens(interval.paused_limiter)].join(" ");
  const kinds = [];
  if (/budget|бюджет|money|баланс|остаток|fund/.test(joined)) kinds.push("budget");
  if (/campaign_limiter|spend_limit|day_limit|daily_limit|limit|лимит|день|day/.test(joined)) kinds.push("limit");
  return kinds;
}

export function summarizePauseIssues(payload, start, end) {
  const rangeStart = new Date(`${start}T00:00:00Z`);
  const rangeEnd = new Date(`${end}T23:59:59.999Z`);
  const summaries = {
    limit: { hours: 0, maxIncidentHours: 0, incidents: 0 },
    budget: { hours: 0, maxIncidentHours: 0, incidents: 0 },
  };

  for (const interval of normalizePauseIntervals(payload)) {
    if (interval.endAt < rangeStart || interval.startAt > rangeEnd) continue;
    const startAt = interval.startAt > rangeStart ? interval.startAt : rangeStart;
    const endAt = interval.endAt < rangeEnd ? interval.endAt : rangeEnd;
    const hours = Math.max((endAt.getTime() - startAt.getTime()) / 3600000, 0);
    if (hours <= 0) continue;
    for (const kind of pauseIssueKinds(interval)) {
      summaries[kind].hours += hours;
      summaries[kind].maxIncidentHours = Math.max(summaries[kind].maxIncidentHours, hours);
      summaries[kind].incidents += 1;
    }
  }

  return summaries;
}
