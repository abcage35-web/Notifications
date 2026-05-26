# Контекст проекта: /контент_уведомление

Этот подпроект формирует ежемесячное уведомление по заполненности контента WB и настройкам рекомендаций продавца.

Подробный общий контекст репозитория: `../PROJECT_CONTEXT.md`.

## Назначение

`wb-marketing-notifications` ищет товары WB, у которых есть план продаж или FBO-остаток, но не заполнены важные блоки карточки:

- рекомендации продавца;
- рич-контент;
- видео.

По итогам отправляется сообщение в Пачку, 3 Markdown-файла и 2 сообщения в тред.

## Файлы

```text
wb-marketing-notifications/
├── PROJECT_CONTEXT.md
├── README.md
├── package.json
├── package-lock.json
├── send_pachca_report.mjs
└── scripts/
    ├── build-products-content-problems-plan-or-fbo-report.mjs
    └── build-seller-recommendations-suggestions.mjs
```

Связанные файлы:

```text
.github/workflows/wb-marketing-notifications.yml
cloudflare/abcage_notification/src/index.js
cloudflare/wb_marketing_notifications/src/index.js
```

## Запуск

Локальная сборка без отправки:

```bash
cd wb-marketing-notifications
npm ci
node scripts/build-products-content-problems-plan-or-fbo-report.mjs
```

Отправка:

```bash
cd wb-marketing-notifications
npm run send
```

Ручной GitHub Actions запуск в тестовый чат:

```bash
gh workflow run "WB Marketing Content Notifications" \
  --repo abcage35-web/Notifications \
  -f pachca_chat_id=39363429 \
  -f report_run_label="ручной запуск"
```

## Автоматизация

Основное расписание для контент-бота задано в отдельном Worker:

```text
cloudflare/wb_marketing_notifications
0 10 20 * * = каждое 20 число месяца в 13:00 МСК
```

Также общий Worker `cloudflare/abcage_notification` умеет обрабатывать резервную команду:

```text
/контент_уведомление
```

Плановый чат: `39531378`.

GitHub workflow:

```text
.github/workflows/wb-marketing-notifications.yml
```

В workflow включен `concurrency`, чтобы новый запуск отменял предыдущий незавершенный запуск этого же отчета.

## Secrets/env

GitHub Actions:

- `ABCAGE_ANALYZER_TOKEN`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_MARKETING`

Cloudflare Worker:

- `GITHUB_TOKEN`
- `DISPATCH_SECRET`
- `PACHCA_WEBHOOK_SECRET`

Worker var:

- `PACHCA_CHAT_ID=39531378`

## Основной сборщик

Файл:

```text
scripts/build-products-content-problems-plan-or-fbo-report.mjs
```

Он делает:

1. Загружает базовый список товаров из MCP/MySQL.
2. Загружает маркетологов/кабинеты из Google Sheets.
3. Загружает CRM ID и ссылки дизайнов из Google Sheets.
4. Читает открытый WB basket `card.json` по каждому артикулу.
5. Фильтрует товары с проблемами контента.
6. Запускает второй скрипт для файла рекомендаций продавца.
7. Формирует:
   - `Незаполненный контент по Артикулам.md`;
   - `Полный контент по Артикулам.md`;
   - текст основного сообщения;
   - текст описания файлов в тред;
   - текст сводки по маркетологам в тред.

## Базовый список товаров

Источник: ABCAGE Analyzer MCP.

Таблицы:

- `mp.mp_core__realtime_stocks_data`
- `mp.mp_core__sales_plan`
- `mp.wb_core__card`

Логика:

```text
stockDate = MAX(date) из realtime_stocks_data для mp='wb'
planMonth = первый день месяца stockDate
```

FBO:

```text
SUM(fbo_real) по WB-артикулу на stockDate
```

План:

```text
SUM(COALESCE(correct_count, planned_count, 0)) по planning_date = planMonth
```

Товар попадает в базовый список, если:

```text
plan_qty > 10
или
FBO > 10
```

## Проверка статусов контента

Источник: открытый WB basket `card.json`.

URL строится так:

```text
https://basket-XX.wbbasket.ru/vol{vol}/part{part}/{nmId}/info/ru/card.json
```

Где:

```text
vol = floor(nmId / 100000)
part = floor(nmId / 1000)
```

Basket host определяется по диапазонам `BASKET_VOL_RANGES`, затем перебираются соседние и все known hosts `01..120`. Успешный host кешируется в `.wb-basket-cache.json`.

Поля:

- `imt_name` или `slug` -> название;
- `subj_name` -> категория;
- `selling.brand_name` -> бренд;
- `has_seller_recommendations` -> наличие рекомендаций продавца;
- `has_rich` -> наличие рич-контента;
- `media.has_video` -> наличие видео.

Проблемы:

```text
Проблема рекомендации: has_seller_recommendations !== true
Проблема рич: has_rich === 0/false
Проблема видео: media.has_video !== true
```

## Google Sheets источники

### Маркетологи и кабинеты

CSV:

```text
https://docs.google.com/spreadsheets/d/1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4/export?format=csv&gid=1574673852
```

Колонки:

- `B` / index `1` - WB-артикул;
- `C` / index `2` - кабинет;
- `H` / index `7` - маркетолог.

### CRM ID и дизайны

CSV:

```text
https://docs.google.com/spreadsheets/d/1SNvaHyFSHy9I1rT24dDYsbGEIid5lndcdHEMhTXLjG4/export?format=csv&gid=373432525
```

Колонки:

- `A` / index `0` - CRM ID;
- `E` / index `4` - ссылки WB, из них парсится артикул;
- `S` / index `18` - ссылки на дизайн.

Если у одного WB-артикула несколько CRM ID или ссылок дизайна, они собираются списком.

## Markdown: незаполненный и полный контент

Файлы:

```text
Незаполненный контент по Артикулам.md
Полный контент по Артикулам.md
```

Одинаковые колонки:

- `CRM ID`
- `Артикул`
- `Дизайн`
- `Название товара`
- `Бренд`
- `Остаток FBO`
- `Категория`
- `Кабинет`
- `Маркетолог`
- `Проблема рекомендации`
- `Проблема рич-контент`
- `Проблема видео`

`Незаполненный контент...` содержит только строки, где хотя бы одна проблема = `да`.

`Полный контент...` содержит весь базовый список, включая строки без проблем.

В оба файла добавляются:

- дата формирования в МСК;
- подсказки для Ассистента;
- блок выгрузки со счетчиками;
- примечания с методикой.

## Рекомендации продавца

Файл:

```text
scripts/build-seller-recommendations-suggestions.mjs
```

Выходы:

```text
Настройки Рекомендаций Продавца.md
seller-recommendations-suggestions.json
```

Источники:

- `mp.mp_core__realtime_stocks_data` - FBO на `stockDate`;
- `mp.mp_core__sales_plan` - план на `planMonth`;
- `mp.wb_core__funnel` - заказы, выручка, открытия карточки за 30 дней;
- `mp.wb_core__card` - название/категория/card/account;
- `mp.accounts` - кабинет.

Период funnel:

```text
ordersTo = stockDate - 1 день
ordersFrom = ordersTo - 29 дней
```

Нормализация кабинетов:

```text
ИП Карпачев -> Паша 1
ИП Сытин -> Стас 1
```

Целевые товары:

```text
нет рекомендаций продавца
и есть кабинет
и есть категория
и есть название
и (planQty > 10 или FBO > 10)
```

Кандидаты:

```text
тот же кабинет
и FBO > 10
и категория релевантна целевой категории
```

Категории связаны через:

- точное совпадение категории;
- прямые правила `DIRECT_CATEGORY_RULES`;
- группы категорий `CATEGORY_GROUPS`;
- похожий первый токен названия категории.

Ранжирование кандидата:

```text
score = categoryAffinity + metricScore
```

`metricScore` учитывает:

- FBO;
- заказы 30д;
- план продаж;
- наличие rich/video у кандидата.

В файл попадает до 6 кандидатов на целевой товар.

## Сообщение в Пачку

Основное сообщение строится функцией `buildPachcaMessage()`.

Содержит:

- заголовок `Незаполненный контент по Артикулам (Ежемесячный / 20 число месяца)`;
- теги маркетологов `@a.beaver @a.manokhin @a.nekrasov`;
- дату формирования;
- фильтр базового списка;
- инструкции маркетологам;
- сводку по количеству строк и проблем.

Инструкции в сообщении:

1. Поставить задачу Ассистенту в Яндекс Трекере, передав файл `Незаполненный контент по Артикулам.md`.
2. Использовать `Полный контент по Артикулам.md` для соединения с отчетом `Список товаров по Выручке ПП`.
3. Скорректировать рекомендации продавца по файлу `Настройки Рекомендаций Продавца.md`.
4. Проконтролировать выполнение задачи Ассистентом.

## Треды

После отправки основного сообщения `send_pachca_report.mjs` создает тред и отправляет туда 2 сообщения.

### Описание файлов

Функция:

```text
buildPachcaThreadMessage()
```

Описывает назначение:

- `Настройки Рекомендаций Продавца.md`;
- `Незаполненный контент по Артикулам.md`;
- `Полный контент по Артикулам.md`.

### Сводка по маркетологам

Функция:

```text
buildPachcaMarketerSummaryMessage()
```

Группировка:

```text
маркетолог -> сегмент кабинета -> тип ошибки -> количество
```

Сегменты:

- `Паша 1` + `Стас 1` -> `Паша 1 + Стас 1`;
- `Паша 2` + `Стас 2` -> `Паша 2 + Стас 2`;
- остальные кабинеты остаются как есть.

Если маркетолога нет:

```text
Без маркетолога: @a.beaver @a.manokhin @a.nekrasov
```

## Отправка

`send_pachca_report.mjs`:

1. Запускает основной build script.
2. Загружает 3 Markdown-файла через Pachca `/uploads`.
3. Отправляет основное сообщение в `discussion`.
4. Создает тред.
5. Отправляет описание файлов в тред.
6. Отправляет summary по маркетологам в тред.

При отправке `link_preview=false`.

## Важные нюансы

- Content-бот написан на Node.js, GitHub Actions использует Node 24.
- `ABCAGE_ANALYZER_TOKEN` может быть взят из env; локально скрипт также умеет искать его в `~/.codex/config.toml`.
- `.wb-basket-cache.json` ускоряет повторные запросы к WB basket, но не должен коммититься.
- Если WB меняет basket host, скрипт перебирает fallback hosts и обновляет кеш.
- Для новых content-проверок лучше добавлять отдельное поле в build rows и синхронно расширять оба Markdown-файла.
