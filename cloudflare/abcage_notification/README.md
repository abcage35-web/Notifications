# abcage_notification

Cloudflare Worker that triggers GitHub Actions workflows for WB notification reports.

The Worker does not build or send the Pachca report itself. It only calls GitHub's `workflow_dispatch` API for:

- repository: `abcage35-web/Notifications`
- FBO workflow: `.github/workflows/wb-fbo-supply-notifications.yml`
- actions workflow: `.github/workflows/wb-action-notifications.yml`
- marketing workflow: `.github/workflows/wb-marketing-notifications.yml`
- XWAY bidder limit workflow: `.github/workflows/xway-limit-notifications.yml`
- ref: `main`

GitHub Actions then runs the existing Python report sender, which sends the Pachca message, Markdown file and optional thread message.

GitHub can return either `204 No Content` or `200 OK` with a `workflow_run_id`; both are treated as successful dispatches.

## Schedule

Cloudflare cron:

```text
0 5 * * * - FBO report, 08:00 MSK
5 5 * * * - actions report, 08:05 MSK
30 5 * * 1 - XWAY bidder limit report, Monday 08:30 MSK
```

## Secrets

Required Cloudflare Worker secrets:

- `GITHUB_TOKEN` - GitHub token that can create workflow dispatch events for `abcage35-web/Notifications`.
- `DISPATCH_SECRET` - bearer token for protected manual HTTP dispatch.
- `PACHCA_WEBHOOK_SECRET` - Pachca outgoing webhook signing secret for `/pachca-command`.

Set them with:

```bash
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put DISPATCH_SECRET
npx wrangler secret put PACHCA_WEBHOOK_SECRET
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

To send a backup report to a specific Pachca chat without changing GitHub Secrets:

```bash
curl -X POST "$WORKER_URL/dispatch" \
  -H "Authorization: Bearer $DISPATCH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"39363429","report_run_label":"ручной запуск"}'
```

To run the actions report:

```bash
curl -X POST "$WORKER_URL/dispatch" \
  -H "Authorization: Bearer $DISPATCH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"workflow":"actions","chat_id":"39363429","report_run_label":"ручной запуск"}'
```

## Pachca Backup Command

The Worker also exposes:

```text
POST /pachca-command
```

Supported command text:

```text
/фбо_уведомление
/действия_уведомление
/контент_уведомление
/биддер_уведомление
```

When this endpoint receives a matching Pachca webhook payload, it extracts the chat id from the payload and dispatches the matching GitHub workflow with `pachca_chat_id` set to that chat. The report is then sent to the chat where the command was called.

The endpoint validates Pachca's `Pachca-Signature` header with `PACHCA_WEBHOOK_SECRET`.
