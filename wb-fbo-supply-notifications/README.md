# WB FBO Supply Notifications

Subproject for WB FBO supply notifications and Pachca-ready Markdown reports.

For detailed continuation context, data-source mapping, business rules and deployment notes, read [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Scripts

- `build_sheet_supplies_md.py` builds the current FBO supply report, text message, thread message and JSON export.
- `send_pachca_report.py` builds the report, sends the text summary to Pachca and attaches the Markdown file.
- `custom_wb_fbo_supplies.py` contains the MCP SQL client and the earlier WB Supplies API decomposition helper.

## Runtime Inputs

The scripts intentionally do not store API tokens in the repository.

- `ABCAGE_ANALYZER_TOKEN` is read from the environment first, then from `~/.codex/config.toml`.
- `GOOGLE_SERVICE_ACCOUNT_JSON` is used for live Google Sheets reads, including private FBO supply tabs.
- `PACHCA_TOKEN` is used to send messages/files through Pachca.
- `PACHCA_CHAT_ID` is the Pachca discussion id that receives the report.
- `REPORT_TZ` can override the report timezone, default is `Asia/Tbilisi`.

Generated report files are ignored by git.

## Daily Automation

GitHub Actions workflow `.github/workflows/wb-fbo-supply-notifications.yml` runs every day at 08:00 Asia/Tbilisi (`04:00 UTC`) and can also be started manually with `workflow_dispatch`.

Required repository secrets:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID`
