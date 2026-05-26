# Контекст проекта: ВБ маркетинг уведомления

Этот файл нужен как стартовый контекст для нового чата без истории переписки.

## Назначение

Подпроект `wb-marketing-notifications` предназначен для отдельной системы уведомлений по маркетингу Wildberries.

Он должен быть независим от текущего FBO-отчета:

- не использовать workflow `WB FBO Supply Notifications`;
- не использовать Worker `abcage_notification`;
- не менять логику `wb-fbo-supply-notifications`;
- иметь свой чат Пачки;
- иметь свой Cloudflare Worker;
- иметь свой GitHub Actions workflow.

## Текущий статус

Реализован ежемесячный отчет по заполненности контента WB.

## Чаты Пачки

Общие test/prod chat id и правила переключения хранятся в корневом `PROJECT_CONTEXT.md`.

## Настройки отчета

1. Чат Пачки: `39531378`.
2. Расписание: каждое 20 число месяца в 13:00 МСК.
3. Источники данных: ABCAGE Analyzer MCP, Google Sheets, открытый WB basket `card.json`.
4. Базовая выборка: план продаж за текущий месяц > 10 или FBO-остаток > 10.
5. Уведомляемые сущности: WB-артикулы, кабинеты, категории, маркетологи.
6. Основное сообщение содержит инструкции маркетологам и общую сводку.
7. К сообщению прикладываются три Markdown-файла.
8. В тред отправляются два отдельных сообщения: описание файлов и сводка по маркетологам / кабинетам / ошибкам.
9. Для строк без маркетолога тегаются `@a.beaver`, `@a.manokhin`, `@a.nekrasov`.
10. Ручной вызов через Пачку: `/контент_уведомление`.

## Предлагаемая структура после реализации

```text
wb-marketing-notifications/
  README.md
  PROJECT_CONTEXT.md
  package.json
  send_pachca_report.mjs
  scripts/
    build-products-content-problems-plan-or-fbo-report.mjs
    build-seller-recommendations-suggestions.mjs

cloudflare/wb_marketing_notifications/
  README.md
  package.json
  wrangler.jsonc
  src/index.js

.github/workflows/wb-marketing-notifications.yml
```

## Принцип работы, который стоит повторить из FBO-проекта

1. Cloudflare Worker отвечает за cron и вызывает GitHub `workflow_dispatch`.
2. GitHub Actions запускает Node.js-скрипт.
3. Node.js-скрипт собирает данные, формирует сообщение, тред и Markdown-файлы.
4. Отправка в Пачку идет через `PACHCA_TOKEN`.
5. Чат задается отдельным secret, чтобы не смешивать уведомления.

## Безопасность

- Не коммитить токены, JSON service account, env-файлы и сгенерированные отчеты.
- Для нового проекта использовать отдельный chat id secret.
- Если Worker будет отдельный, использовать отдельный `DISPATCH_SECRET`.

## Secrets

GitHub Actions:

- `ABCAGE_ANALYZER_TOKEN`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_MARKETING`

Cloudflare Worker:

- `GITHUB_TOKEN`
- `DISPATCH_SECRET`
- `PACHCA_WEBHOOK_SECRET`
