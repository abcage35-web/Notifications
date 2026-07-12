# WB Articles Report Notifications

Daily WB article-level marketer report for Pachca.

## Scripts

- `build_wb_articles_marketer_report.py` builds the Markdown report, cabinet MTD message, niche summary, niche detail thread message and JSON summary.
- `send_pachca_report.py` sends two root messages: the cabinet MTD report with its attachment and the niche summary; it creates a thread on the niche summary and posts niche details there.

## Runtime Inputs

- `ABCAGE_ANALYZER_TOKEN` is read by the shared MCP SQL helper.
- `PACHCA_TOKEN` is used to send messages/files through Pachca.
- `PACHCA_CHAT_ID` is the Pachca discussion id that receives the report.
- `REPORT_TZ` controls date calculation, default is `Europe/Moscow`.
- `REPORT_RUN_LABEL` is shown in the message title, default is `09:00 по МСК`.
- `REPORT_WINDOW_DAYS` controls the output window, default is `30`.
- Rows are included only when there is finance revenue or RK spend. FBO is shown as a reference column, not as a filter.
- The second root message contains the marketer/niche summary. Its thread covers MTD revenue/plan, DRR fact/plan, RK spend, orders fact/plan, current FBO and active SKU count.
- Niche turnover is current FBO divided by average daily MTD orders and is displayed in days.
- Active niche SKU means MTD finance revenue above 5,000 RUB or MTD RK spend above 5,000 RUB.
- Niches with zero active SKU are omitted from the thread report.
- Detailed niche metrics are sent only to the thread of the niche summary message.
- Within each marketer, niches are grouped by season type; detailed headings place season type between niche name and active SKU count.
- The marketer summary uses `•` / `• •` bullet levels like the root report and has blank lines only between marketers.
- Revenue and order plans are prorated through the report date; green revenue status starts at 90% completion, and green DRR means fact is not above plan.
- Niches are sorted by spend share descending in both the marketer summary and the detail thread.

Generated report files are ignored by git.

## Automation

GitHub Actions workflow `.github/workflows/wb-articles-report-notifications.yml` can be started manually through `workflow_dispatch`.

The daily schedule is owned by Cloudflare Worker `cloudflare/abcage_notification`, which calls GitHub's workflow dispatch API every day at 09:00 Moscow time (`06:00 UTC`).

Manual Pachca backup command:

```text
/отчет_уведомление
```

Production chat: `39531378`. Test chat: `39363429`.
