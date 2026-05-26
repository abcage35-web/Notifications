# WB Articles Report Notifications

Daily WB article-level marketer report for Pachca.

## Scripts

- `build_wb_articles_marketer_report.py` builds the Markdown report, Pachca message and JSON summary.
- `send_pachca_report.py` builds the report, sends the message to Pachca and attaches the Markdown file.

## Runtime Inputs

- `ABCAGE_ANALYZER_TOKEN` is read by the shared MCP SQL helper.
- `PACHCA_TOKEN` is used to send messages/files through Pachca.
- `PACHCA_CHAT_ID` is the Pachca discussion id that receives the report.
- `REPORT_TZ` controls date calculation, default is `Europe/Moscow`.
- `REPORT_RUN_LABEL` is shown in the message title, default is `09:00 по МСК`.
- `REPORT_WINDOW_DAYS` controls the output window, default is `30`.
- `REPORT_MIN_CURRENT_FBO` controls the current stock filter, default is `10`.

Generated report files are ignored by git.

## Automation

GitHub Actions workflow `.github/workflows/wb-articles-report-notifications.yml` can be started manually through `workflow_dispatch`.

The daily schedule is owned by GitHub Actions `schedule`, which runs every day at 09:00 Moscow time (`06:00 UTC`). Cloudflare Worker `cloudflare/abcage_notification` is used for the manual Pachca backup command.

Manual Pachca backup command:

```text
/отчет_уведомление
```

Production chat: `39531378`. Test chat: `39363429`.
