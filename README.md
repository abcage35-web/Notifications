# Notifications

WB FBO notification/report scripts for building Pachca-ready Markdown summaries.

## Current scripts

- `build_sheet_supplies_md.py` builds the current FBO supply report, text message, thread message and JSON export.
- `custom_wb_fbo_supplies.py` contains the MCP SQL client and the earlier WB Supplies API decomposition helper.

## Runtime inputs

The scripts intentionally do not store API tokens in the repository.

- `ABCAGE_ANALYZER_TOKEN` is read from the environment first, then from `~/.codex/config.toml`.
- `REPORT_TZ` can override the report timezone, default is `Asia/Tbilisi`.
- `PACHCA_CHAT_ID` can override the test chat id used by helper code, default is `39363429`.

Generated report files are ignored by git.
