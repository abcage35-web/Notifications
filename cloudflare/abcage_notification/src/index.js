const GITHUB_API_VERSION = "2026-03-10";

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

function cleanInputs(inputs = {}) {
  return Object.fromEntries(
    Object.entries(inputs)
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "")
      .map(([key, value]) => [key, String(value).trim()]),
  );
}

async function readJson(request) {
  const text = await request.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
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

function isFboBackupCommand(text) {
  const normalized = String(text || "").trim().toLowerCase();
  return normalized === "/фбо_уведомление";
}

async function dispatchWorkflow(env, source, inputs = {}) {
  const owner = requireEnv(env, "GITHUB_OWNER");
  const repo = requireEnv(env, "GITHUB_REPO");
  const workflowId = requireEnv(env, "GITHUB_WORKFLOW_ID");
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
        schedule: "0 5 * * *",
        backupCommands: ["/фбо_уведомление"],
      });
    }

    if (request.method === "POST" && url.pathname === "/dispatch") {
      if (!isAuthorized(request, env, url)) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const payload = await readJson(request);
        const pachcaChatId = pickFirstString(payload.pachca_chat_id, payload.chat_id);
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
      if (!isAuthorized(request, env, url)) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const payload = await readJson(request);
        const text = extractPachcaCommandText(payload);
        if (!isFboBackupCommand(text)) {
          return jsonResponse({ ok: true, ignored: true, reason: "not an FBO backup command" });
        }

        const pachcaChatId = extractPachcaChatId(payload);
        if (!pachcaChatId) {
          return jsonResponse({ ok: false, error: "Pachca chat id not found in webhook payload" }, 400);
        }

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

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(
      dispatchWorkflow(env, "cloudflare-cron")
        .then((result) => console.log(JSON.stringify(result)))
        .catch((error) => {
          console.error(error);
          throw error;
        }),
    );
  },
};
