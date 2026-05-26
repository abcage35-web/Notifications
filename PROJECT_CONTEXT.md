# Контекст репозитория Notifications

Этот документ нужен как главный контекст для нового чата без истории переписки. Если нужно дорабатывать проект, сначала читать этот файл, затем `PROJECT_CONTEXT.md` внутри нужного подпроекта.

Репозиторий: `abcage35-web/Notifications`.

## Текущие боты

В репозитории сейчас 5 рабочих ботов:

| Бот | Папка | Команда Пачки | Плановый чат | Расписание |
|---|---|---|---|---|
| FBO-поставки WB | `wb-fbo-supply-notifications/` | `/фбо_уведомление` | `36815841` через `PACHCA_CHAT_ID` | каждый день 08:00 МСК |
| Предустановленные действия WB | `wb-action-notifications/` | `/действия_уведомление` | `36815841` через `PACHCA_CHAT_ID_ACTIONS` | каждый день 08:05 МСК |
| Контент WB | `wb-marketing-notifications/` | `/контент_уведомление` | `39531378` через `PACHCA_CHAT_ID_MARKETING` или Worker var | каждое 20 число в 13:00 МСК |
| Проблемы биддера XWAY | `xway-limit-notifications/` | `/биддер_уведомление` | `39531378` через `PACHCA_CHAT_ID_XWAY_LIMITS` | каждый понедельник 08:30 МСК |
| Артикулярный отчет WB | `wb-articles-report-notifications/` | `/отчет_уведомление` | `39531378` через `PACHCA_CHAT_ID_REPORT` или fallback workflow | каждый день 09:00 МСК через GitHub Actions schedule |

Тестовый чат для ручных прогонов: `39363429`.

Правило: продовый чат не использовать для тестов без явной просьбы. Для ручных тестов передавать `pachca_chat_id=39363429` или вызывать команду из тестового чата.

## Структура репозитория

```text
.
├── .github/
│   └── workflows/
│       ├── wb-action-notifications.yml
│       ├── wb-articles-report-notifications.yml
│       ├── wb-fbo-supply-notifications.yml
│       ├── wb-marketing-notifications.yml
│       └── xway-limit-notifications.yml
├── cloudflare/
│   ├── abcage_notification/
│   │   ├── README.md
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   ├── wrangler.jsonc
│   │   └── src/index.js
│   └── wb_marketing_notifications/
│       ├── README.md
│       ├── package.json
│       ├── package-lock.json
│       ├── wrangler.jsonc
│       └── src/index.js
├── wb-action-notifications/
│   ├── PROJECT_CONTEXT.md
│   ├── README.md
│   ├── build_action_report.py
│   ├── requirements.txt
│   └── send_pachca_report.py
├── wb-articles-report-notifications/
│   ├── PROJECT_CONTEXT.md
│   ├── README.md
│   ├── build_wb_articles_marketer_report.py
│   ├── requirements.txt
│   └── send_pachca_report.py
├── wb-fbo-supply-notifications/
│   ├── PROJECT_CONTEXT.md
│   ├── README.md
│   ├── build_sheet_supplies_md.py
│   ├── custom_wb_fbo_supplies.py
│   ├── requirements.txt
│   └── send_pachca_report.py
├── wb-marketing-notifications/
│   ├── PROJECT_CONTEXT.md
│   ├── README.md
│   ├── package.json
│   ├── package-lock.json
│   ├── send_pachca_report.mjs
│   └── scripts/
│       ├── build-products-content-problems-plan-or-fbo-report.mjs
│       └── build-seller-recommendations-suggestions.mjs
├── xway-limit-notifications/
│   ├── PROJECT_CONTEXT.md
│   ├── README.md
│   ├── package.json
│   ├── package-lock.json
│   ├── send_pachca_report.mjs
│   ├── lib/
│   │   └── xway-api.mjs
│   └── scripts/
│       └── build-xway-limit-reports.mjs
├── .gitignore
├── PROJECT_CONTEXT.md
└── README.md
```

Сгенерированные отчеты (`pachca_*.md`, `pachca_*.json`, `Незаполненный контент...md`, `Полный контент...md`, `Настройки Рекомендаций...md`, `seller-recommendations-suggestions.json`, `.wb-basket-cache.json`) не являются исходниками и не должны коммититься.

## Последние важные изменения

Текущая ветка `main` включает эти ключевые изменения:

- FBO и actions перенесены на Cloudflare cron через GitHub `workflow_dispatch`.
- Добавлен резервный ручной запуск из Пачки через команды `/фбо_уведомление`, `/действия_уведомление`, `/контент_уведомление`.
- Для БЗО добавлен резолв сотрудника через Pachca `/users`, чтобы тег был настоящим mention `<@user_id>`, а не просто текстом.
- Actions-бот получил сегменты `НАСТРОИТЬ ЦЕНУ`, `ВКЛЮЧИТЬ БЗО`, `СОЗДАТЬ РК`, `ВЫКЛЮЧИТЬ РК`, `ПРОВЕРИТЬ АКТИВНОСТЬ РК`.
- Для `ПРОВЕРИТЬ АКТИВНОСТЬ РК` добавлены метрики оборачиваемости и ДРР; блок в сообщении сгруппирован по маркетологу, затем по категории; временно исключается категория `Колготки`.
- Для `ВЫКЛЮЧИТЬ РК` добавлено условие `Траты (вчера) >= 1000 руб.`, чтобы не показывать товар, если правка уже успела отработать.
- Добавлен контент-бот WB с тремя Markdown-файлами и ежемесячным расписанием.
- Для WB basket `card.json` добавлено ускорение и кеширование определения basket host.
- Добавлен XWAY-бот `/биддер_уведомление`: еженедельно присылает проблемы лимитов/бюджетов, вылеты лимитов и автоисключения поиска; название, категория и FBO берутся из ABCAGE Analyzer DB.
- Добавлен артикулярный отчет WB `/отчет_уведомление`: ежедневно в 09:00 МСК отправляет 30-дневный Markdown-файл и сообщение с ДРР MTD по IP/кабинетам и общим WB.

## Общая архитектура

Боты работают по одной схеме:

```text
Cloudflare cron или исходящий webhook Пачки
        ↓
Cloudflare Worker
        ↓
GitHub REST API workflow_dispatch
        ↓
GitHub Actions
        ↓
Python/Node builder
        ↓
Pachca API: сообщение + файлы + треды
```

Cloudflare Worker не собирает бизнес-данные. Он только выбирает нужный workflow и передает inputs:

- `pachca_chat_id` - override чата для ручного/резервного запуска;
- `report_run_label` - подпись времени в заголовке отчета.

Расчет метрик, фильтры, формат сообщений и отправка в Пачку находятся в подпроектах.

## Cloudflare Workers

### `cloudflare/abcage_notification`

Общий диспетчер для FBO, actions, XWAY, артикулярного отчета и резервной команды content.

Файл: `cloudflare/abcage_notification/src/index.js`.

Cron triggers из `wrangler.jsonc`:

```text
0 5 * * * - FBO, 08:00 МСК
5 5 * * * - actions, 08:05 МСК
30 5 * * 1 - XWAY bidder limits, каждый понедельник 08:30 МСК
```

Артикулярный отчет WB запускается по расписанию через GitHub Actions `schedule` (`0 6 * * *`), чтобы не увеличивать число Cloudflare cron-триггеров сверх лимита аккаунта. Worker поддерживает для него ручную команду `/отчет_уведомление`.

Поддерживаемые команды Пачки:

```text
/фбо_уведомление
/действия_уведомление
/контент_уведомление
/биддер_уведомление
/отчет_уведомление
```

Endpoints:

- `GET /health` - проверка Worker и списка расписаний/команд.
- `POST /dispatch` - защищенный ручной запуск через `Authorization: Bearer <DISPATCH_SECRET>`, `x-dispatch-secret` или query `?secret=...`.
- `POST /pachca-command` - вход для исходящего webhook Пачки. Проверяет `Pachca-Signature` через `PACHCA_WEBHOOK_SECRET`, вынимает текст команды и chat id из payload, запускает workflow в том чате, где команду вызвали.

Важные env/vars:

- `GITHUB_OWNER=abcage35-web`
- `GITHUB_REPO=Notifications`
- `GITHUB_REF=main`
- `GITHUB_FBO_WORKFLOW_ID=wb-fbo-supply-notifications.yml`
- `GITHUB_ACTIONS_WORKFLOW_ID=wb-action-notifications.yml`
- `GITHUB_MARKETING_WORKFLOW_ID=wb-marketing-notifications.yml`
- `GITHUB_XWAY_LIMIT_WORKFLOW_ID=xway-limit-notifications.yml`
- `GITHUB_REPORT_WORKFLOW_ID=wb-articles-report-notifications.yml`

Secrets:

- `GITHUB_TOKEN`
- `DISPATCH_SECRET`
- `PACHCA_WEBHOOK_SECRET`

### `cloudflare/wb_marketing_notifications`

Отдельный Worker для ежемесячного контент-бота.

Файл: `cloudflare/wb_marketing_notifications/src/index.js`.

Cron trigger:

```text
0 10 20 * * - каждое 20 число месяца в 13:00 МСК
```

Команда:

```text
/контент_уведомление
```

По расписанию отправляет workflow `wb-marketing-notifications.yml` в `PACHCA_CHAT_ID`, по умолчанию `39531378`.

## GitHub Actions

### `.github/workflows/wb-fbo-supply-notifications.yml`

Запускает Python 3.12 в папке `wb-fbo-supply-notifications/`.

Секреты:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID`

Команда:

```bash
python send_pachca_report.py
```

Артефакты:

```text
wb-fbo-supply-notifications/pachca_fbo_supplies_sheet_*.md
wb-fbo-supply-notifications/pachca_fbo_supplies_sheet_*.json
```

### `.github/workflows/wb-action-notifications.yml`

Запускает Python 3.12 в папке `wb-action-notifications/`.

Секреты:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_ACTIONS`

Fallback чата: `39363429`, если secret не задан.

Команда:

```bash
python send_pachca_report.py
```

### `.github/workflows/wb-marketing-notifications.yml`

Запускает Node.js 24 в папке `wb-marketing-notifications/`.

Секреты:

- `ABCAGE_ANALYZER_TOKEN`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_MARKETING`

Команда:

```bash
npm run send
```

Есть `concurrency`:

```text
wb-marketing-content-notifications-${{ github.ref }}
```

Новый запуск отменяет предыдущий незавершенный запуск этого же workflow/ref, чтобы не отправлять дубль контент-отчета.

### `.github/workflows/xway-limit-notifications.yml`

Запускает Node.js 24 в папке `xway-limit-notifications/`.

Секреты:

- `ABCAGE_ANALYZER_TOKEN`
- `XWAY_STORAGE_STATE_JSON`
- `PACHCA_TOKEN_XWAY_LIMITS`
- `PACHCA_CHAT_ID_XWAY_LIMITS`

Команда:

```bash
npm run send
```

Есть `concurrency`:

```text
xway-limit-notifications-${{ github.ref }}
```

Workflow принимает `pachca_chat_id`, `report_run_label`, `report_start`, `report_end`.

### `.github/workflows/wb-articles-report-notifications.yml`

Запускает Python 3.12 в папке `wb-articles-report-notifications/`.

Секреты:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_REPORT`

Fallback чата для расписания: `39531378`, если secret не задан. Для тестового ручного прогона передавать `pachca_chat_id=39363429`.

Команда:

```bash
python send_pachca_report.py
```

Артефакты:

```text
wb-articles-report-notifications/wb_articles_marketer_metrics_*.md
wb-articles-report-notifications/wb_articles_marketer_metrics_*.json
```

## Общие источники данных

### ABCAGE Analyzer MCP

Python-боты используют `wb-fbo-supply-notifications/custom_wb_fbo_supplies.py`, Node-боты используют встроенный класс `McpSql`.

Endpoint:

```text
https://mcp.mpvibe.ru/mcp/analyzer
```

Токен:

```text
ABCAGE_ANALYZER_TOKEN
```

Tool:

```text
sql__mysql_query
```

Основные таблицы:

- `mp.mp_core__realtime_stocks_data` - текущие FBO-остатки.
- `mp.mp_core__realtime_prices` - текущие цены до СПП, цена с СПП, процент СПП.
- `mp.wb_core__price` - fallback по ценам.
- `mp.wb_core__card` - WB-артикул, barcode, название, категория, card/account binding.
- `mp.wb_core__order` - заказы.
- `mp.wb_core__campaign`, `mp.wb_core__campaign_card`, `mp.wb_core__campaign_stat_daily_sku` - РК, статусы, привязка к SKU, траты.
- `mp.wb_core__supply`, `mp.wb_core__supply_contents` - фактически принятые поставки.
- `mp.mp_core__sales_plan` - план продаж.
- `mp.wb_core__funnel` - агрегированные funnel/order/open-card метрики для контента и рекомендаций продавца.
- `mp.accounts` - кабинет/account alias для контент-бота.

### Google Sheets

1. Ответственные маркетологи:

```text
spreadsheet: 1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4
gid: 1574673852
```

Для FBO/actions используется `D1:H430`:

- `D` - WB-артикул;
- `H` - тег маркетолога.

Для content используется CSV всего листа:

- `B` - WB-артикул;
- `C` - кабинет;
- `H` - тег маркетолога.

2. Менеджеры:

```text
spreadsheet: 1FWuNKO08UeuxCX4DI_S0gMmqLImCQXMVLPSMQ_tXWRI
gid: 586703293
range: C1:F3492
```

- `C` - WB-артикул;
- `F` - имя менеджера.

Маппинг:

```text
Оля -> @o.eshmakova
Никита -> @n.aisin
Максим -> @m.gorokhov
```

3. Будущие поставки FBO:

```text
spreadsheet: 1kLX5hGPK3g8HRno39POiHheg9UIFXNkKQGKcpAXX1KM
tabs:
  - ВБ. Новый, gid 876111045, range C:O
  - ВБ. Регионы, gid 1978923499, range C:O
```

Индексы внутри `C:O`:

- `C` / index `0` - дата;
- `L` / index `9` - строка товара;
- `M` / index `10` - внутренний/поставочный артикул;
- `N` / index `11` - barcode;
- `O` / index `12` - количество.

Поставки суммируются по WB-артикулу и дате, включая строки из обеих вкладок.

4. Дизайны для content:

```text
spreadsheet: 1SNvaHyFSHy9I1rT24dDYsbGEIid5lndcdHEMhTXLjG4
gid: 373432525
```

- `A` - CRM ID;
- `E` - ссылки на WB-артикулы;
- `S` - ссылки на дизайн.

### Wildberries public APIs

1. БЗО, отзывы и рейтинг:

```text
GET https://card.wb.ru/cards/v4/detail
```

Параметры:

```text
appType=1
curr=rub
dest=-1257786
spp=30
ab_testing=false
nm=<артикулы через ;>
```

Поля:

- `products[].feedbackPoints` -> БЗО;
- `products[].nmFeedbacks` -> количество отзывов;
- `products[].nmReviewRating` -> рейтинг.

2. Контент карточки:

```text
GET https://basket-XX.wbbasket.ru/vol{vol}/part{part}/{nmId}/info/ru/card.json
```

Поля:

- `imt_name` или `slug` -> название;
- `subj_name` -> категория;
- `selling.brand_name` -> бренд;
- `has_seller_recommendations` -> есть рекомендации продавца;
- `has_rich` -> есть рич-контент;
- `media.has_video` -> есть видео.

Для ускорения Node-боты кешируют соответствие `vol -> basket host` в `.wb-basket-cache.json`. Этот файл не нужно коммитить.

### Pachca API

Base URL:

```text
https://api.pachca.com/api/shared/v1
```

Используется:

- `POST /uploads` - получить S3/direct upload поля;
- upload файла в `direct_url`;
- `POST /messages` - отправить сообщение в `discussion` или `thread`;
- `POST /messages/{message_id}/thread` - создать тред;
- `GET /users?query=...` - найти сотрудника для настоящего mention `<@user_id>` по имени.

## Бот 1: FBO-поставки WB

Папка: `wb-fbo-supply-notifications/`.

Главные файлы:

- `build_sheet_supplies_md.py` - собирает данные, правила, Markdown и текст сообщения.
- `send_pachca_report.py` - запускает сборку, грузит файл, отправляет сообщение и тред.
- `custom_wb_fbo_supplies.py` - MCP SQL helper.
- `PROJECT_CONTEXT.md` - детальный контекст именно этого бота.

### Что отправляет

1. Основное сообщение в Пачку:

```text
ПОСТАВКИ FBO WB (отчет 08:00 по МСК)
```

2. Markdown-файл:

```text
pachca_fbo_supplies_sheet_YYYY-MM-DD.md
```

3. Тред к сообщению, только если есть товары без маркетолога:

```text
@a.nekrasov, добавь, пожалуйста, ответственных маркетологов за артикулами:
```

### Источники метрик

| Метрика | Источник | Логика |
|---|---|---|
| Принятая поставка вчера+сегодня | `mp.wb_core__supply`, `mp.wb_core__supply_contents` | `count_fact`, период `START-1` включительно до `START+1` не включительно, группировка по `sku`, дата в отчете = `START` |
| Будущая поставка | Google Sheets поставок, вкладки `ВБ. Новый`, `ВБ. Регионы` | дата из `C`, товар из `L`, barcode из `N`, количество из `O`; суммы складываются по артикулу/дате |
| Название и категория | `mp.wb_core__card` | `short_name`, `object`; сопоставление по SKU/barcode |
| Текущий FBO | `mp.mp_core__realtime_stocks_data` | последняя дата, сумма `fbo_real` по SKU |
| Наличие РК | `mp.wb_core__campaign_card`, `mp.wb_core__campaign`, fallback `campaign.sku_list` | неархивные states `4`, `9`, `11`; считается `rk_created`, count, ids |
| Траты РК (3д) | `mp.wb_core__campaign_stat_daily_sku` | `START-2`, `START-1`, `START` |
| Заказы (7д) | `mp.wb_core__order` | `START-6` по `START`, не отмененные, distinct `srid`/`order_number` |
| Цена / СПП | `mp.mp_core__realtime_prices`, fallback `mp.wb_core__price` | цена до СПП, цена с СПП, процент СПП |
| БЗО | `card.wb.ru/cards/v4/detail` | `feedbackPoints`; `>0` значит БЗО есть |
| Отзывы | `card.wb.ru/cards/v4/detail` | `nmFeedbacks` |
| Рейтинг | `card.wb.ru/cards/v4/detail` | `nmReviewRating` |
| Маркетолог | Google Sheets маркетологов | WB-артикул из `D`, тег из `H` |
| Менеджер | Google Sheets менеджеров | WB-артикул из `C`, имя из `F`, маппинг в тег |

### Логика попадания в текстовое сообщение

Markdown содержит полный список за 3 дня, а текстовое сообщение содержит только товары под условия.

Блок `ВЧЕРА и СЕГОДНЯ`:

```text
принятая поставка > 0
и
FBO до прихода = текущий FBO - принятое количество <= 100
```

Текущий FBO может стать больше 100 после приемки, поэтому для вчера/сегодня используется остаток до прихода.

Блок `ЗАВТРА`:

```text
плановая поставка > 0
и
текущий FBO < 100
```

`Послезавтра` остается в Markdown-файле, но в текстовое сообщение не выводится.

### Рекомендации в FBO-сообщении

Рекомендации выводятся вложенными строками `↳`. Если рекомендаций нет, строка `↳` не пишется.

Порядок:

1. Цена.
2. БЗО.
3. РК.

Условия:

- `ЦЕНА: ПРОВЕРИТЬ ЦЕНУ`: `FBO >= 50` и `цена до СПП >= 80000`.
- `БЗО: ВКЛЮЧИТЬ БЗО`: `FBO >= 50`, `feedbackPoints <= 0`, `отзывов <= 10`, `заказов 7д <= 10`.
- `РК: СОЗДАТЬ РК`: `FBO >= 50` и нет неархивной РК.
- `РК: ПРОВЕРИТЬ АКТИВНОСТЬ РК`: только для `ВЧЕРА и СЕГОДНЯ`; `FBO >= 50`, РК есть, траты (3д) `< 3000`.

БЗО дополнительно тегает сотрудника, найденного через Pachca `/users` по `PACHCA_BZO_MENTION_QUERY` (по умолчанию `Елена Ханжова`). Если не найдено, fallback `@Елена Ханжова`.

## Бот 2: Предустановленные действия WB

Папка: `wb-action-notifications/`.

Главные файлы:

- `build_action_report.py` - собирает все товары с FBO > 0, обогащает метриками, строит сегменты.
- `send_pachca_report.py` - отправляет сообщение и Markdown-файл.
- `PROJECT_CONTEXT.md` - детальный контекст именно этого бота.

### Что отправляет

Основное сообщение:

```text
ПРЕДУСТАНОВЛЕННЫЕ ДЕЙСТВИЯ WB (отчет 08:05 по МСК)
```

Markdown-файл:

```text
pachca_wb_actions_YYYY-MM-DD.md
```

Тред не создается.

### Базовый список

Источник:

```text
mp.wb_core__card
mp.mp_core__realtime_stocks_data
```

Берутся товары WB, у которых на последнюю дату есть `fbo_real > 0`.

### Метрики

| Метрика | Источник | Логика |
|---|---|---|
| FBO | `mp.mp_core__realtime_stocks_data` | последняя дата, `SUM(fbo_real)` |
| Название/категория | `mp.wb_core__card` | `short_name`, `object` |
| РК есть | FBO helper `load_rk_by_article()` | states `4`, `9`, `11`, `campaign_card` + `sku_list` |
| Траты (3д) | FBO helper `load_ad_spend_by_article()` | включая сегодня: `START-2`..`START` |
| Траты (3д без сегодня) | `mp.wb_core__campaign_stat_daily_sku` | `START-3`..`START-1` |
| Траты (вчера) | `mp.wb_core__campaign_stat_daily_sku` | `START-1` |
| Заказы (7д) | FBO helper `load_orders_7d_by_article()` | `START-6`..`START`, distinct order key |
| Заказы/выручка (3д без сегодня) | `mp.wb_core__order` | `START-3`..`START-1`, не отмененные |
| Оборачиваемость (3д) | расчет | `FBO / (orders_3d_excl_today / 3)` |
| ДРР (3д без сегодня) | расчет | `spend_3d_excl_today / revenue_3d_excl_today * 100` |
| Цена / СПП | FBO helper `load_price_by_article()` | realtime prices, fallback WB price |
| БЗО/отзывы/рейтинг | WB `card.wb.ru/cards/v4/detail` | `feedbackPoints`, `nmFeedbacks`, `nmReviewRating` |
| Ближайшая поставка | Google Sheets FBO поставок | ближайшая дата в горизонте 30 дней от `START`, суммы по артикулу/дате |
| Менеджер | FBO helper `load_manager_by_article()` | Google Sheets менеджеров |
| Маркетолог | FBO helper `load_marketer_by_article()` | Google Sheets маркетологов |

### Сегменты и условия

Сегменты выводятся в таком порядке:

1. `НАСТРОИТЬ ЦЕНУ`
2. `ВКЛЮЧИТЬ БЗО`
3. `СОЗДАТЬ РК`
4. `ВЫКЛЮЧИТЬ РК`
5. `ПРОВЕРИТЬ АКТИВНОСТЬ РК`

Условия:

```text
НАСТРОИТЬ ЦЕНУ:
FBO >= 50
и цена до СПП >= 80000
```

```text
ВКЛЮЧИТЬ БЗО:
FBO >= 50
и feedbackPoints <= 0
и отзывов <= 10
и заказов 7д <= 10
```

```text
СОЗДАТЬ РК:
FBO >= 50
и нет неархивной РК
```

```text
ВЫКЛЮЧИТЬ РК:
РК есть
и оборачиваемость 3 полных дней < 5д
и (траты 3д без сегодня > 3000 или ДРР 3д без сегодня > 4%)
и траты вчера >= 1000
и ближайшая поставка отсутствует или через 5+ дней
```

Условие `траты вчера >= 1000` важно: если вчера траты уже ниже 1000, считаем, что ошибка/правка уже отработала, и товар не нужно подсвечивать.

```text
ПРОВЕРИТЬ АКТИВНОСТЬ РК:
FBO >= 50
и РК есть
и траты 3д включая сегодня < 3000
и оборачиваемость > 30д
и категория не во временных исключениях
```

Временное исключение:

```text
CHECK_RK_EXCLUDED_CATEGORIES=Колготки
```

Категория `Колготки` исключается из сообщения и Markdown-таблицы для `ПРОВЕРИТЬ АКТИВНОСТЬ РК`.

### Формат сообщения

Обычные сегменты выводятся по строкам:

```text
• `article` / FBO: `value` / Метрика: `value` / Название @ответственный
```

`ПРОВЕРИТЬ АКТИВНОСТЬ РК` в сообщении группируется:

```text
ПРОВЕРИТЬ АКТИВНОСТЬ РК:
• @Маркетолог
• • **Категория** / SKU: `N` / `article`, `article`
```

Категории в этой группировке жирные.

БЗО в actions-боте дополнительно призывает Елену Ханжову через Pachca mention, как и FBO-бот.

## Бот 3: Контент WB

Папка: `wb-marketing-notifications/`.

Главные файлы:

- `scripts/build-products-content-problems-plan-or-fbo-report.mjs` - основной отчет по заполненности контента.
- `scripts/build-seller-recommendations-suggestions.mjs` - расчет рекомендаций продавца.
- `send_pachca_report.mjs` - отправка трех Markdown-файлов и тредов.
- `PROJECT_CONTEXT.md` - детальный контекст именно этого бота.

### Что отправляет

Основное сообщение:

```text
Незаполненный контент по Артикулам
```

К нему прикрепляются 3 файла:

```text
Настройки Рекомендаций Продавца.md
Незаполненный контент по Артикулам.md
Полный контент по Артикулам.md
```

После основного сообщения создается тред, куда отправляются:

1. описание файлов;
2. сводка по маркетологам / кабинетам / ошибкам.

### Базовый список товаров

Источник:

```text
mp.mp_core__realtime_stocks_data
mp.mp_core__sales_plan
mp.wb_core__card
```

Логика:

- `stockDate` = последняя дата остатков WB из `mp.mp_core__realtime_stocks_data`;
- `planMonth` = первый день месяца `stockDate`;
- товар попадает в базу, если `plan_qty > 10` или `FBO > 10`;
- план берется из `correct_count`, fallback `planned_count`;
- FBO берется как сумма `fbo_real`.

### Проверка контента

Для каждого WB-артикула читается открытый WB basket `card.json`:

```text
https://basket-XX.wbbasket.ru/vol{vol}/part{part}/{nmId}/info/ru/card.json
```

Поля:

- `has_seller_recommendations !== true` -> проблема рекомендации;
- `has_rich === false/0` -> проблема рич-контента;
- `media.has_video !== true` -> проблема видео.

Файл `Незаполненный контент по Артикулам.md` содержит только товары, где есть хотя бы одна проблема.

Файл `Полный контент по Артикулам.md` содержит весь базовый список, включая товары без проблем.

### Ответственные и дизайн

Маркетологи и кабинеты:

```text
spreadsheet: 1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4
gid: 1574673852
CSV export
```

- `B` - WB-артикул;
- `C` - кабинет;
- `H` - маркетолог.

Дизайны:

```text
spreadsheet: 1SNvaHyFSHy9I1rT24dDYsbGEIid5lndcdHEMhTXLjG4
gid: 373432525
CSV export
```

- `A` - CRM ID;
- `E` - ссылки на WB карточки;
- `S` - ссылки на дизайн.

Если маркетолог отсутствует, в summary thread для него используется строка:

```text
Без маркетолога: @a.beaver @a.manokhin @a.nekrasov
```

### Рекомендации продавца

Скрипт `build-seller-recommendations-suggestions.mjs` строит файл `Настройки Рекомендаций Продавца.md`.

Источники:

- `mp.mp_core__realtime_stocks_data` - FBO на `stockDate`;
- `mp.mp_core__sales_plan` - план за `planMonth`;
- `mp.wb_core__funnel` - заказы, выручка, открытия карточки за последние 30 дней до `stockDate` без сегодняшнего дня;
- `mp.wb_core__card` - карточка/категория;
- `mp.accounts` - кабинет.

Нормализация кабинетов:

```text
ИП Карпачев -> Паша 1
ИП Сытин -> Стас 1
```

Цели:

- товары без рекомендаций продавца;
- `plan_qty > 10` или `FBO > 10`;
- есть кабинет, категория, название.

Кандидаты:

- только тот же кабинет/ИП;
- `FBO > 10`;
- релевантная категория по жестким связкам или группе категорий.

Ранжирование кандидатов:

- близость категории;
- FBO;
- заказы 30д;
- план продаж;
- наличие rich/video у кандидата.

В детализации выводится топ до 6 артикулов для рекомендации.

### Сообщение content-бота

Основное сообщение содержит:

- дату формирования в МСК;
- фильтр базового списка;
- инструкцию маркетологам;
- сводку по количеству проблем: рекомендации, rich, видео.

Тред:

- описание трех файлов;
- агрегированная сводка по маркетологу, сегменту кабинетов и типам ошибок.

Сегменты кабинетов в summary:

- `Паша 1` + `Стас 1` объединяются в `Паша 1 + Стас 1`;
- `Паша 2` + `Стас 2` объединяются в `Паша 2 + Стас 2`.

## Безопасность

Не коммитить:

- токены;
- JSON service account;
- `.env`;
- сгенерированные отчеты;
- локальные cache-файлы.

Секреты GitHub:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID`
- `PACHCA_CHAT_ID_ACTIONS`
- `PACHCA_CHAT_ID_MARKETING`
- `PACHCA_TOKEN_XWAY_LIMITS`
- `PACHCA_CHAT_ID_XWAY_LIMITS`
- `XWAY_STORAGE_STATE_JSON`

Секреты Cloudflare:

- `GITHUB_TOKEN`
- `DISPATCH_SECRET`
- `PACHCA_WEBHOOK_SECRET`

Google service account, который ранее использовался для чтения таблиц:

```text
abcage-notify-parser@notification-abcage.iam.gserviceaccount.com
```

Он должен иметь reader-доступ ко всем Google Sheets, которые читают Python-боты.

## Как запускать

### Локально без отправки

FBO:

```bash
cd wb-fbo-supply-notifications
python -m pip install -r requirements.txt
python build_sheet_supplies_md.py
```

Actions:

```bash
cd wb-action-notifications
python -m pip install -r requirements.txt
python build_action_report.py
```

Content:

```bash
cd wb-marketing-notifications
npm ci
node scripts/build-products-content-problems-plan-or-fbo-report.mjs
```

XWAY bidder limits:

```bash
cd xway-limit-notifications
npm ci
npm run build
```

### Отправка вручную через GitHub Actions

```bash
gh workflow run "WB FBO Supply Notifications" --repo abcage35-web/Notifications -f pachca_chat_id=39363429 -f report_run_label="ручной запуск"
gh workflow run "WB Action Notifications" --repo abcage35-web/Notifications -f pachca_chat_id=39363429 -f report_run_label="ручной запуск"
gh workflow run "WB Marketing Content Notifications" --repo abcage35-web/Notifications -f pachca_chat_id=39363429 -f report_run_label="ручной запуск"
gh workflow run "XWAY Limit Notifications" --repo abcage35-web/Notifications -f pachca_chat_id=39363429 -f report_run_label="ручной запуск"
```

### Отправка через Cloudflare `/dispatch`

```bash
curl -X POST "$WORKER_URL/dispatch" \
  -H "Authorization: Bearer $DISPATCH_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"workflow":"fbo","chat_id":"39363429","report_run_label":"ручной запуск"}'
```

Для actions:

```json
{"workflow":"actions","chat_id":"39363429","report_run_label":"ручной запуск"}
```

Для content:

```json
{"workflow":"marketing","chat_id":"39363429","report_run_label":"ручной запуск"}
```

Для XWAY bidder limits:

```json
{"workflow":"xway_limits","chat_id":"39363429","report_run_label":"ручной запуск"}
```

### Резервный запуск из Пачки

В чате с ботом написать одну из команд:

```text
/фбо_уведомление
/действия_уведомление
/контент_уведомление
/биддер_уведомление
```

Если Пачка требует обращение к боту, допускается:

```text
@Slave_Marketing_Bot /фбо_уведомление
```

Worker нормализует текст и убирает начальный mention.

## Как вносить изменения

1. Определить, к какому боту относится изменение.
2. Читать `PROJECT_CONTEXT.md` этого подпроекта.
3. Менять только сборщик нужного бота и, если нужно, его workflow/Worker routing.
4. Если меняется условие сегмента, обновить:
   - код условия;
   - текст условия в Markdown;
   - сообщение в Пачку;
   - этот контекст.
5. Если меняется расписание, синхронно обновить:
   - `wrangler.jsonc`;
   - `src/index.js` defaultRunLabel/schedule label;
   - README/PROJECT_CONTEXT;
   - заголовок сообщения, если там указано время.
6. Если меняется чат, убедиться, что это тестовый или продовый запуск по явной просьбе.

## Важные нюансы

- В Пачке обычные Markdown-переносы могут склеиваться. Python-боты добавляют два пробела перед `\n`, чтобы получить hard line break.
- Для визуальной вложенности в сообщениях используется символ `↳`, а не nested Markdown list: Пачка нестабильно рендерит настоящие вложенные списки.
- Артикулы и важные числовые метрики оборачиваются в backticks, чтобы их было удобно копировать.
- СПП не контролируется нами. Мы можем менять только цену до СПП, но в отчетах часто показывается пара `цена / СПП` как ориентир.
- Для БЗО в Markdown-файле фактическая колонка БЗО показывает `нет` или `да (<сумма>)`; рекомендация `ВКЛЮЧИТЬ БЗО` живет в колонке действия или тексте сообщения.
