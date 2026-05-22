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

function isAuthorized(request, env) {
  const secret = requireEnv(env, "DISPATCH_SECRET");
  const authorization = request.headers.get("authorization") || "";
  return authorization === `Bearer ${secret}`;
}

async function dispatchWorkflow(env, source) {
  const owner = requireEnv(env, "GITHUB_OWNER");
  const repo = requireEnv(env, "GITHUB_REPO");
  const workflowId = requireEnv(env, "GITHUB_WORKFLOW_ID");
  const ref = env.GITHUB_REF || "main";
  const token = requireEnv(env, "GITHUB_TOKEN");
  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "abcage-notification-cloudflare-worker",
      "x-github-api-version": GITHUB_API_VERSION,
    },
    body: JSON.stringify({ ref }),
  });

  if (response.status !== 204) {
    const body = await response.text();
    throw new Error(
      `GitHub workflow_dispatch failed: ${response.status} ${response.statusText} ${body}`,
    );
  }

  return {
    ok: true,
    source,
    owner,
    repo,
    workflowId,
    ref,
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
        schedule: "31 14 * * *",
      });
    }

    if (request.method === "POST" && url.pathname === "/dispatch") {
      if (!isAuthorized(request, env)) {
        return jsonResponse({ ok: false, error: "unauthorized" }, 401);
      }

      try {
        const result = await dispatchWorkflow(env, "manual-http");
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
