# wb_marketing_notifications

Cloudflare Worker for the monthly WB marketing content notification.

## Schedule

```text
0 10 20 * * - каждое 20 число месяца в 13:00 МСК
```

The Worker calls GitHub Actions workflow `.github/workflows/wb-marketing-notifications.yml`.

## Manual Dispatch

```bash
curl -X POST "$WORKER_URL/dispatch" \
  -H "Authorization: Bearer $DISPATCH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"39531378","report_run_label":"ручной запуск"}'
```

## Pachca Command

`POST /pachca-command` supports:

```text
/контент_уведомление
```

The endpoint validates `Pachca-Signature` with `PACHCA_WEBHOOK_SECRET` or accepts the protected dispatch secret for manual testing.
