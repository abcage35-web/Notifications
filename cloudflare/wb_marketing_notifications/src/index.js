const GITHUB_API_VERSION = "2026-03-10";
const COMMAND = "/контент_уведомление";

function requireEnv(env, name) {
  const value = env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function cleanInputs(inputs = {}) {
  return Object.fromEntries(
    Object.entries(inputs)
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
      .map(([key, value]) => [key, String(value).trim()]),
  );
}

function parseJson(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

async function readJson(request) {
  return parseJson(await request.text());
}

function pickFirstString(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return "";
}

function isAuthorized(request, env, url) {
  const secret = requireEnv(env, "DISPATCH_SECRET");
  const authorization = request.headers.get("authorization") || "";
  const headerSecret = request.headers.get("x-dispatch-secret") || "";
  const querySecret = url.searchParams.get("secret") || "";
  return authorization === `Bearer ${secret}` || headerSecret === secret || querySecret === secret;
}

function toHex(buffer) {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function hasValidPachcaSignature(request, env, rawBody) {
  const secret = env.PACHCA_WEBHOOK_SECRET;
  const signature = request.headers.get("pachca-signature") || "";
  if (!secret || !signature || !rawBody) return false;

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(rawBody));
  return toHex(digest) === signature;
}

function extractPachcaChatId(payload) {
  const message = payload.message || payload.data?.message || payload.data || {};
  return pickFirstString(
    payload.pachca_chat_id,
    payload.chat_id,
    payload.entity_id,
    message.chat_id,
    message.root_chat_id,
    message.entity_id,
    payload.entity?.id,
  );
}

function extractPachcaCommandText(payload) {
  const message = payload.message || payload.data?.message || payload.data || {};
  return pickFirstString(payload.content, payload.text, message.content, message.text);
}

function normalizeCommandText(text) {
  return String(text || "").trim().toLowerCase().replace(/^@\S+\s+/, "").trim();
}

async function dispatchWorkflow(env, source, inputs = {}) {
  const owner = requireEnv(env, "GITHUB_OWNER");
  const repo = requireEnv(env, "GITHUB_REPO");
  const workflowId = requireEnv(env, "GITHUB_WORKFLOW_ID");
  const ref = env.GITHUB_REF || "main";
  const token = requireEnv(env, "GITHUB_TOKEN");
  const workflowInputs = cleanInputs(inputs);
  const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "wb-marketing-notifications-cloudflare-worker",
      "x-github-api-version": GITHUB_API_VERSION,
    },
    body: JSON.stringify(Object.keys(workflowInputs).length ? { ref, inputs: workflowInputs } : { ref }),
  });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(`GitHub workflow_dispatch failed: ${response.status} ${response.statusText} ${body}`);
  }
  return {
    ok: true,
    source,
    githubStatus: response.status,
    owner,
    repo,
    workflowId,
    ref,
    inputs: workflowInputs,
    dispatchedAt: new Date().toISOString(),
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        worker: "wb_marketing_notifications",
        schedule: "0 10 20 * *",
        scheduleMsk: "каждое 20 число месяца в 13:00 МСК",
        command: COMMAND,
      });
    }

    if (request.method === "POST" && url.pathname === "/dispatch") {
      if (!isAuthorized(request, env, url)) return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      try {
        const payload = await readJson(request);
        const pachcaChatId = pickFirstString(payload.pachca_chat_id, payload.chat_id, env.PACHCA_CHAT_ID);
        const reportRunLabel = pickFirstString(payload.report_run_label, "ручной запуск");
        const result = await dispatchWorkflow(env, "manual-http", {
          pachca_chat_id: pachcaChatId,
          report_run_label: reportRunLabel,
        });
        return jsonResponse(result, 202);
      } catch (error) {
        console.error(error);
        return jsonResponse({ ok: false, error: String(error.message || error) }, 502);
      }
    }

    if (request.method === "POST" && url.pathname === "/pachca-command") {
      const rawBody = await request.text();
      const payload = parseJson(rawBody);
      const webhookTimestamp = Number(payload.webhook_timestamp || 0);
      const isFreshWebhook = webhookTimestamp ? Math.abs(Date.now() / 1000 - webhookTimestamp) <= 120 : true;
      const isPachcaSigned = isFreshWebhook && (await hasValidPachcaSignature(request, env, rawBody));

      if (!isAuthorized(request, env, url) && !isPachcaSigned) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const text = normalizeCommandText(extractPachcaCommandText(payload));
        if (text !== COMMAND) return jsonResponse({ ok: true, ignored: true, reason: "not content command" });

        const pachcaChatId = extractPachcaChatId(payload);
        if (!pachcaChatId) return jsonResponse({ ok: false, error: "Pachca chat id not found in webhook payload" }, 400);

        const result = await dispatchWorkflow(env, "pachca-command", {
          pachca_chat_id: pachcaChatId,
          report_run_label: "ручной запуск",
        });
        return jsonResponse(result, 202);
      } catch (error) {
        console.error(error);
        return jsonResponse({ ok: false, error: String(error.message || error) }, 502);
      }
    }

    return jsonResponse({ ok: false, error: "not found" }, 404);
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      dispatchWorkflow(env, "cloudflare-cron", {
        pachca_chat_id: env.PACHCA_CHAT_ID || "39531378",
        report_run_label: "13:00 по МСК",
      })
        .then((result) => console.log(JSON.stringify({ ...result, cron: controller?.cron })))
        .catch((error) => {
          console.error(error);
          throw error;
        }),
    );
  },
};
