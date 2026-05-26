# Notifications

Repository for WB/Pachca notification bots.

The project is split into independent subprojects. Each bot builds a report, sends a Pachca message, attaches Markdown files, and can be triggered by Cloudflare cron, GitHub Actions `workflow_dispatch`, or a Pachca backup command.

Full operational context is documented in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Bots

| Bot | Folder | Pachca command | Schedule | Main output |
|---|---|---|---|---|
| FBO supplies | `wb-fbo-supply-notifications/` | `/фбо_уведомление` | every day 08:00 MSK | FBO supply message + Markdown file + optional thread for missing marketers |
| WB actions | `wb-action-notifications/` | `/действия_уведомление` | every day 08:05 MSK | action segments by price, BZO, RK creation, RK shutdown, RK activity |
| Content | `wb-marketing-notifications/` | `/контент_уведомление` | every 20th day 13:00 MSK | content completeness message + 3 Markdown files + thread summaries |
| XWAY bidder limits | `xway-limit-notifications/` | `/биддер_уведомление` | every Monday 08:30 MSK | bidder limit/budget, limit activity and auto-exclusion reports |
| WB articles report | `wb-articles-report-notifications/` | `/отчет_уведомление` | every day 09:00 MSK | 30-day article-level marketer Markdown report + MTD DRR message |

## Repository Structure

```text
.
├── .github/workflows/
│   ├── wb-action-notifications.yml
│   ├── wb-articles-report-notifications.yml
│   ├── wb-fbo-supply-notifications.yml
│   ├── wb-marketing-notifications.yml
│   └── xway-limit-notifications.yml
├── cloudflare/
│   ├── abcage_notification/
│   └── wb_marketing_notifications/
├── xway-limit-notifications/
├── wb-action-notifications/
├── wb-fbo-supply-notifications/
├── wb-marketing-notifications/
├── PROJECT_CONTEXT.md
└── README.md
```

## Runtime Flow

```text
Cloudflare cron or Pachca command
        ↓
Cloudflare Worker
        ↓
GitHub Actions workflow_dispatch
        ↓
Python/Node report builder
        ↓
Pachca API message + files + optional thread
```

The Cloudflare Workers do not calculate report data. They only dispatch the correct GitHub Actions workflow. Business logic stays in the bot folders.

## Secrets

Secrets are not committed. The active bots use:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON` for Python Google Sheets readers
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID`
- `PACHCA_CHAT_ID_ACTIONS`
- `PACHCA_CHAT_ID_MARKETING`
- `PACHCA_CHAT_ID_REPORT`
- `PACHCA_TOKEN_XWAY_LIMITS`
- `PACHCA_CHAT_ID_XWAY_LIMITS`
- `XWAY_STORAGE_STATE_JSON`
- Cloudflare Worker secrets: `GITHUB_TOKEN`, `DISPATCH_SECRET`, `PACHCA_WEBHOOK_SECRET`

Generated report files are ignored and should not be committed.
