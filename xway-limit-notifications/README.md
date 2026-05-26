# XWAY Limit Notifications

Weekly Pachca bot for bidder/XWAY limit problem reports.

## What It Sends

- `1. Проблемы: настройка лимитов и бюджетов.md`
- `2. Проблемы: вылеты лимитов.md`
- `3. Проблемы: Автоисключения Поиска.md`
- `Инструкция: отчеты по проблемам лимитов.md`

The Pachca message contains a short summary by marketer. Files contain the full tables.

## Schedule

Cloudflare cron dispatches the GitHub Actions workflow every Monday at `08:30 MSK`.

Manual Pachca command:

```text
/биддер_уведомление
```

## Runtime Inputs

Required env vars:

- `ABCAGE_ANALYZER_TOKEN` - ABCAGE Analyzer MCP token for product name/category/FBO enrichment.
- `XWAY_STORAGE_STATE_JSON` or `XWAY_STORAGE_STATE_BASE64` - XWAY authenticated storage state.
- `PACHCA_TOKEN` - Pachca bot token.
- `PACHCA_CHAT_ID` - Pachca discussion id.

Optional:

- `REPORT_START` / `REPORT_END` - override the default period.
- `REPORT_RUN_LABEL` - label in the Pachca message title.

Default period is the last 3 days ending yesterday by Moscow time.

## Run Locally

```bash
npm ci
npm run build
```

To send:

```bash
npm run send
```

Generated reports are ignored by git.
