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

Создан каркас подпроекта. Бизнес-логика еще не реализована.

## Чаты Пачки

Общие test/prod chat id и правила переключения хранятся в корневом `PROJECT_CONTEXT.md`.

## Что нужно определить перед разработкой

1. ID чата Пачки для отправки уведомлений.
2. Расписание запуска: время, timezone, дни недели.
3. Источники данных: WB API, ABCAGE Analyzer MCP, Google Sheets или другое.
4. Условия попадания объектов в уведомление.
5. Какие сущности уведомляем: товары, РК, кабинеты, категории, маркетологи.
6. Формат текстового сообщения.
7. Нужен ли Markdown-файл.
8. Нужен ли тред к сообщению.
9. Кого тегать в сообщении/треде.
10. Нужны ли отдельные secrets/env vars.

## Предлагаемая структура после реализации

```text
wb-marketing-notifications/
  README.md
  PROJECT_CONTEXT.md
  build_report.py
  send_pachca_report.py
  requirements.txt

cloudflare/wb_marketing_notifications/
  README.md
  package.json
  wrangler.jsonc
  src/index.js

.github/workflows/wb-marketing-notifications.yml
```

## Принцип работы, который стоит повторить из FBO-проекта

1. Cloudflare Worker отвечает за cron и вызывает GitHub `workflow_dispatch`.
2. GitHub Actions запускает Python-скрипт.
3. Python-скрипт собирает данные, формирует сообщение и при необходимости Markdown-файл.
4. Отправка в Пачку идет через `PACHCA_TOKEN`.
5. Чат задается отдельным secret, чтобы не смешивать уведомления.

## Безопасность

- Не коммитить токены, JSON service account, env-файлы и сгенерированные отчеты.
- Для нового проекта использовать отдельный chat id secret.
- Если Worker будет отдельный, использовать отдельный `DISPATCH_SECRET`.
