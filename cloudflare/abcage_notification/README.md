# abcage_notification

Cloudflare Worker that triggers the existing GitHub Actions workflow for WB FBO supply notifications.

The Worker does not build or send the Pachca report itself. It only calls GitHub's `workflow_dispatch` API for:

- repository: `abcage35-web/Notifications`
- workflow: `.github/workflows/wb-fbo-supply-notifications.yml`
- ref: `main`

GitHub Actions then runs the existing Python report sender, which sends the Pachca message, Markdown file and optional thread message.

## Schedule

Cloudflare cron:

```text
31 14 * * *
```

This is `17:31 MSK`.

## Secrets

Required Cloudflare Worker secrets:

- `GITHUB_TOKEN` - GitHub token that can create workflow dispatch events for `abcage35-web/Notifications`.
- `DISPATCH_SECRET` - bearer token for protected manual HTTP dispatch.

Set them with:

```bash
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put DISPATCH_SECRET
```

## Deploy

```bash
cd cloudflare/abcage_notification
npx wrangler deploy
```

## Manual Test

```bash
curl -X POST "$WORKER_URL/dispatch" \
  -H "Authorization: Bearer $DISPATCH_SECRET"
```

This manual test triggers the real GitHub workflow, so it will send the report to Pachca.
