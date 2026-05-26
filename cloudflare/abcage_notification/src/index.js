const GITHUB_API_VERSION = "2026-03-10";

const REPORTS = {
  fbo: {
    key: "fbo",
    command: "/фбо_уведомление",
    workflowEnv: "GITHUB_FBO_WORKFLOW_ID",
    fallbackWorkflowEnv: "GITHUB_WORKFLOW_ID",
    defaultWorkflowId: "wb-fbo-supply-notifications.yml",
    defaultRunLabel: "08:00 по МСК",
    cron: "0 5 * * *",
  },
  actions: {
    key: "actions",
    command: "/действия_уведомление",
    workflowEnv: "GITHUB_ACTIONS_WORKFLOW_ID",
    defaultWorkflowId: "wb-action-notifications.yml",
    defaultRunLabel: "08:05 по МСК",
    cron: "5 5 * * *",
  },
  marketing: {
    key: "marketing",
    command: "/контент_уведомление",
    workflowEnv: "GITHUB_MARKETING_WORKFLOW_ID",
    defaultWorkflowId: "wb-marketing-notifications.yml",
    defaultRunLabel: "ручной запуск",
    cron: "",
  },
};

function requireEnv(env, name) {
  const value = env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
    },
  });
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
  if (!secret || !signature || !rawBody) {
    return false;
  }

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

function cleanInputs(inputs = {}) {
  return Object.fromEntries(
    Object.entries(inputs)
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
      .map(([key, value]) => [key, String(value).trim()]),
  );
}

function parseJson(text) {
  if (!text) {
    return {};
  }
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
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return "";
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
  const normalized = String(text || "").trim().toLowerCase();
  return normalized.replace(/^@\S+\s+/, "").trim();
}

function reportByKey(reportKey) {
  const normalized = String(reportKey || "").trim().toLowerCase();
  const aliases = {
    action: "actions",
    actions: "actions",
    "wb-action-notifications.yml": "actions",
    fbo: "fbo",
    "wb-fbo-supply-notifications.yml": "fbo",
    content: "marketing",
    marketing: "marketing",
    "wb-marketing-notifications.yml": "marketing",
  };
  return REPORTS[aliases[normalized] || normalized] || REPORTS.fbo;
}

function reportByCommand(text) {
  const normalized = normalizeCommandText(text);
  return Object.values(REPORTS).find((report) => normalized === report.command);
}

function reportByCron(cron) {
  return Object.values(REPORTS).find((report) => report.cron && report.cron === cron) || REPORTS.fbo;
}

function reportByPayload(payload, url) {
  return reportByKey(
    pickFirstString(
      payload.workflow,
      payload.report,
      payload.report_key,
      url.searchParams.get("workflow"),
      url.searchParams.get("report"),
    ),
  );
}

function workflowIdForReport(env, report) {
  return (
    env[report.workflowEnv] ||
    (report.fallbackWorkflowEnv ? env[report.fallbackWorkflowEnv] : "") ||
    report.defaultWorkflowId
  );
}

async function dispatchWorkflow(env, source, inputs = {}, reportKey = "fbo") {
  const report = reportByKey(reportKey);
  const owner = requireEnv(env, "GITHUB_OWNER");
  const repo = requireEnv(env, "GITHUB_REPO");
  const workflowId = workflowIdForReport(env, report);
  const ref = env.GITHUB_REF || "main";
  const token = requireEnv(env, "GITHUB_TOKEN");
  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`;
  const workflowInputs = cleanInputs(inputs);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "abcage-notification-cloudflare-worker",
      "x-github-api-version": GITHUB_API_VERSION,
    },
    body: JSON.stringify(
      Object.keys(workflowInputs).length ? { ref, inputs: workflowInputs } : { ref },
    ),
  });

  const body = await response.text();
  let payload = {};
  if (body) {
    try {
      payload = JSON.parse(body);
    } catch {
      payload = { body };
    }
  }

  if (!response.ok) {
    throw new Error(
      `GitHub workflow_dispatch failed: ${response.status} ${response.statusText} ${body}`,
    );
  }

  return {
    ok: true,
    source,
    githubStatus: response.status,
    workflowRunId: payload.workflow_run_id,
    runUrl: payload.html_url || payload.run_url,
    owner,
    repo,
    report: report.key,
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
        worker: "abcage_notification",
        schedules: Object.fromEntries(
          Object.values(REPORTS).filter((report) => report.cron).map((report) => [report.key, report.cron]),
        ),
        backupCommands: Object.values(REPORTS).map((report) => report.command),
      });
    }

    if (request.method === "POST" && url.pathname === "/dispatch") {
      if (!isAuthorized(request, env, url)) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const payload = await readJson(request);
        const report = reportByPayload(payload, url);
        const pachcaChatId = pickFirstString(payload.pachca_chat_id, payload.chat_id);
        const reportRunLabel = pickFirstString(payload.report_run_label, "ручной запуск");
        const result = await dispatchWorkflow(env, "manual-http", {
          pachca_chat_id: pachcaChatId,
          report_run_label: reportRunLabel,
        }, report.key);
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
      const isFreshWebhook = webhookTimestamp
        ? Math.abs(Date.now() / 1000 - webhookTimestamp) <= 120
        : true;
      const isPachcaSigned = isFreshWebhook && (await hasValidPachcaSignature(request, env, rawBody));

      if (!isAuthorized(request, env, url) && !isPachcaSigned) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const text = extractPachcaCommandText(payload);
        const report = reportByCommand(text);
        if (!report) {
          return jsonResponse({ ok: true, ignored: true, reason: "not a supported backup command" });
        }

        const pachcaChatId = extractPachcaChatId(payload);
        if (!pachcaChatId) {
          return jsonResponse({ ok: false, error: "Pachca chat id not found in webhook payload" }, 400);
        }

        const result = await dispatchWorkflow(env, "pachca-command", {
          pachca_chat_id: pachcaChatId,
          report_run_label: "ручной запуск",
        }, report.key);
        return jsonResponse(result, 202);
      } catch (error) {
        console.error(error);
        return jsonResponse({ ok: false, error: String(error.message || error) }, 502);
      }
    }

    return jsonResponse({ ok: false, error: "not found" }, 404);
  },

  async scheduled(controller, env, ctx) {
    const report = reportByCron(controller?.cron);
    ctx.waitUntil(
      dispatchWorkflow(env, "cloudflare-cron", {
        report_run_label: report.defaultRunLabel,
      }, report.key)
        .then((result) => console.log(JSON.stringify(result)))
        .catch((error) => {
          console.error(error);
          throw error;
        }),
    );
  },
};
