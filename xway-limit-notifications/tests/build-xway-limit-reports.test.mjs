import assert from "node:assert/strict";
import test from "node:test";

import { XwayApiClient, autoRuleProblem, isAutoRuleConfigured, normalizeAutoRule } from "../lib/xway-api.mjs";
import { aggregateAutoExclusionRows } from "../scripts/build-xway-limit-reports.mjs";

function problemRow(overrides = {}) {
  return {
    article: "123456789",
    shopId: 1,
    productId: 10,
    productUrl: "https://am.xway.ru/wb/shop/1/product/10",
    productName: "Тестовый товар",
    category: "Тестовая категория",
    marketer: "@marketer",
    fbo: 100,
    campaignId: 1000,
    campaignType: "Единая ставка",
    problem: "выключено",
    ruleText: "правило выключено",
    clustersWithSpend: 2,
    fixedClusters: 1,
    spend: 100,
    orders: 3,
    ...overrides,
  };
}

test("aggregates auto-exclusion problems into one row per SKU", () => {
  const rows = aggregateAutoExclusionRows([
    problemRow(),
    problemRow({
      campaignId: 1001,
      campaignType: "Ручная ставка: поиск",
      problem: "нет условий",
      ruleText: "нет условий",
      clustersWithSpend: 5,
      fixedClusters: 2,
      spend: 250,
      orders: 4,
    }),
    problemRow({ article: "987654321", campaignId: 2000, spend: 50 }),
  ]);

  assert.equal(rows.length, 2);
  const row = rows.find((item) => item.article === "123456789");
  assert.equal(row.problemCount, 2);
  assert.deepEqual(row.correctionPlaces, [
    "Единая ставка: выключено, правило выключено",
    "Ручная ставка: поиск: нет условий",
  ]);
  assert.equal(row.clustersWithSpend, 7);
  assert.equal(row.fixedClusters, 3);
  assert.equal(row.spend, 350);
  assert.equal(row.orders, 7);
});

test("counts the same problematic campaign type once and ignores duplicate campaign rows", () => {
  const rows = aggregateAutoExclusionRows([
    problemRow(),
    problemRow(),
    problemRow({ campaignId: 1002, problem: "не настроено", ruleText: "правило не настроено", spend: 20 }),
  ]);

  assert.equal(rows.length, 1);
  assert.equal(rows[0].problemCount, 1);
  assert.deepEqual(rows[0].correctionPlaces, [
    "Единая ставка: выключено, не настроено, правило выключено, правило не настроено",
  ]);
  assert.equal(rows[0].spend, 120);
});

test("recognizes the active exclude-all-unfixed response from /exclude-rule", () => {
  const rule = normalizeAutoRule({
    is_active: true,
    mode: "EXCLUDE_ALL_UNFIXED",
    dispatcher_active: false,
    rules: [],
  });

  assert.equal(rule.active, true);
  assert.equal(rule.mode, "EXCLUDE_ALL_UNFIXED");
  assert.equal(isAutoRuleConfigured(rule), true);
});

test("loads auto-exclusion rules from the current /exclude-rule endpoint", async () => {
  const originalFetch = globalThis.fetch;
  const requestedUrls = [];
  globalThis.fetch = async (url) => {
    requestedUrls.push(String(url));
    return new Response(JSON.stringify({ is_active: true, mode: "EXCLUDE_ALL_UNFIXED", rules: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    const client = new XwayApiClient({ XWAY_COOKIE_HEADER: "sessionid=test" }, { start: "2026-07-17", end: "2026-07-19" });
    await client.campaignAutoExcludeRule(1, 2, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestedUrls.length, 1);
  assert.match(requestedUrls[0], /\/api\/adv\/shop\/1\/product\/2\/campaign\/3\/exclude-rule$/);
});

test("requires active conditions for the CONDITIONS mode", () => {
  const emptyRule = normalizeAutoRule({ is_active: true, mode: "CONDITIONS", rules: [] });
  assert.equal(isAutoRuleConfigured(emptyRule), false);
  assert.deepEqual(autoRuleProblem(emptyRule), { problem: "нет условий", rule: "нет активных условий" });

  const configuredRule = normalizeAutoRule({
    is_active: true,
    mode: "CONDITIONS",
    rules: [{ is_frozen: false, conditions: [{ condition_type: "METRIC" }] }],
  });
  assert.equal(isAutoRuleConfigured(configuredRule), true);
});
