# Контекст проекта: /действия_уведомление

Этот подпроект формирует отдельное сообщение и Markdown-файл с предустановленными действиями по товарам WB.

Подробный общий контекст репозитория: `../PROJECT_CONTEXT.md`.

## Назначение

`wb-action-notifications` каждый день собирает все товары WB с FBO-остатком и раскладывает их по сегментам действий:

- `НАСТРОИТЬ ЦЕНУ`
- `ВКЛЮЧИТЬ БЗО`
- `СОЗДАТЬ РК`
- `ВЫКЛЮЧИТЬ РК`
- `ПРОВЕРИТЬ АКТИВНОСТЬ РК`

Цель: дать ответственным короткий список операционных действий по цене, БЗО и рекламе без привязки к конкретной поставке.

## Файлы

```text
wb-action-notifications/
├── PROJECT_CONTEXT.md
├── README.md
├── build_action_report.py
├── requirements.txt
└── send_pachca_report.py
```

Связанные файлы:

```text
.github/workflows/wb-action-notifications.yml
cloudflare/abcage_notification/src/index.js
```

`build_action_report.py` переиспользует helpers из `../wb-fbo-supply-notifications/build_sheet_supplies_md.py`, поэтому изменения общих источников менеджеров, маркетологов, БЗО, цены и РК часто надо проверять сразу в двух ботах.

## Запуск

Локальная сборка без отправки:

```bash
cd wb-action-notifications
python -m pip install -r requirements.txt
python build_action_report.py
```

Отправка в Пачку:

```bash
cd wb-action-notifications
python send_pachca_report.py
```

Ручной GitHub Actions запуск в тестовый чат:

```bash
gh workflow run "WB Action Notifications" \
  --repo abcage35-web/Notifications \
  -f pachca_chat_id=39363429 \
  -f report_run_label="ручной запуск"
```

## Автоматизация

Плановый запуск идет через общий Worker `cloudflare/abcage_notification`.

Расписание:

```text
5 5 * * * = 08:05 МСК
```

Пачка-команда:

```text
/действия_уведомление
```

По расписанию workflow берет чат из `PACHCA_CHAT_ID_ACTIONS`. Сейчас продовый чат: `36815841`. Для теста передавать `pachca_chat_id=39363429`.

## Secrets/env

GitHub Actions:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID_ACTIONS`

Переменные в коде с defaults:

- `ACTION_MIN_FBO=50`
- `PRICE_ACTION_THRESHOLD=80000`
- `RK_LOW_SPEND_THRESHOLD=3000`
- `RK_DISABLE_YESTERDAY_SPEND_THRESHOLD=1000`
- `DRR_DISABLE_THRESHOLD=4`
- `TURNOVER_DISABLE_DAYS=5`
- `SUPPLY_LOOKAHEAD_DAYS=30`
- `SUPPLY_DISABLE_MIN_DAYS=5`
- `CHECK_RK_EXCLUDED_CATEGORIES=Колготки`

## Источники данных

### Базовый список товаров

`load_base_rows()` читает:

- `mp.mp_core__realtime_stocks_data`
- `mp.wb_core__card`

Условие:

```text
последняя дата остатков
и FBO > 0
```

Поля:

- `sku` -> WB-артикул;
- `short_name` -> название;
- `object` -> категория;
- `SUM(fbo_real)` -> FBO.

### Наличие РК

Функция из FBO-модуля: `load_rk_by_article()`.

Источники:

- `mp.wb_core__campaign_card`
- `mp.wb_core__campaign`
- fallback по `campaign.sku_list`

Считаются неархивные РК со states:

```text
4, 9, 11
```

В результате:

- `rk_created`
- `rk_count`
- `rk_campaign_ids`

### Траты РК

1. Траты (3д), включая сегодня:

Функция FBO helper `load_ad_spend_by_article()`.

Период:

```text
START-2 .. START
```

Источник:

```text
mp.wb_core__campaign_stat_daily_sku.consumptions
```

2. Траты (3д без сегодня):

Локальная функция `load_ad_spend_3d_excluding_today()`.

Период:

```text
START-3 .. START-1
```

3. Траты (вчера):

Локальная функция `load_ad_spend_yesterday_by_article()`.

Период:

```text
START-1
```

### Заказы, выручка, оборачиваемость, ДРР

Заказы (7д):

- FBO helper `load_orders_7d_by_article()`;
- `mp.wb_core__order`;
- период `START-6 .. START`;
- только `COALESCE(is_cancel, 0) = 0`;
- distinct `COALESCE(NULLIF(srid, ''), order_number)`.

Заказы/выручка (3д без сегодня):

- `load_orders_3d_excluding_today()`;
- `mp.wb_core__order`;
- период `START-3 .. START-1`;
- только неотмененные;
- дедуп по `COALESCE(NULLIF(srid, ''), order_number)`.

Расчеты:

```text
Оборачиваемость (3д) = FBO / (orders_3d_excl_today / 3)
ДРР (3д без сегодня) = ad_spend_3d_excl_today / revenue_3d_excl_today * 100
```

Если заказов за 3 дня нет, оборачиваемость = `None` и такие товары не попадают в условия, где нужна оборачиваемость.

### Цена / СПП

Функция FBO helper `load_price_by_article()`.

Основной источник:

```text
mp.mp_core__realtime_prices
```

Fallback:

```text
mp.wb_core__price
```

Поля:

- цена до СПП;
- цена с СПП;
- процент СПП.

Для действия цены используется только цена до СПП.

### БЗО, отзывы, рейтинг

Функция FBO helper `load_wb_card_metrics_by_article()`.

Источник:

```text
GET https://card.wb.ru/cards/v4/detail
```

Поля:

- `feedbackPoints` -> БЗО;
- `nmFeedbacks` -> отзывы;
- `nmReviewRating` -> рейтинг.

### Ближайшая поставка FBO

`load_nearest_supplies()` читает те же Google Sheets поставок, что FBO-бот:

- `ВБ. Новый`
- `ВБ. Регионы`
- range `C:O`

Берется ближайшая дата от `START` до `START + 30 дней`, поставки суммируются по WB-артикулу и дате.

Если поставки нет в горизонте 30 дней, в сообщении и Markdown ставится `-`.

### Ответственные

Маркетолог:

- FBO helper `load_marketer_by_article()`;
- таблица маркетологов;
- WB-артикул из `D`;
- тег из `H`.

Менеджер:

- FBO helper `load_manager_by_article()`;
- таблица менеджеров;
- WB-артикул из `C`;
- имя из `F`;
- маппинг `Оля`, `Никита`, `Максим`.

БЗО-призыв:

- FBO helper `bzo_employee_mention()`;
- ищет сотрудника Пачки по `PACHCA_BZO_MENTION_QUERY`;
- возвращает `<@user_id>` или fallback.

## Условия сегментов

### НАСТРОИТЬ ЦЕНУ

```text
FBO >= ACTION_MIN_FBO
и price_before_spp >= PRICE_ACTION_THRESHOLD
```

Default:

```text
FBO >= 50
и цена до СПП >= 80000
```

В сообщении выводится:

```text
• `article` / FBO: `...` / Цена: `... ₽` / Название @manager
```

### ВКЛЮЧИТЬ БЗО

```text
FBO >= 50
и feedbackPoints <= 0
и nmFeedbacks <= 10
и orders_7d <= 10
```

В сообщении выводится менеджер и дополнительно Елена Ханжова:

```text
... @manager / <@user_id Елены>
```

### СОЗДАТЬ РК

```text
FBO >= 50
и rk_created = false
```

В сообщении ответственный - маркетолог.

### ВЫКЛЮЧИТЬ РК

```text
rk_created = true
и turnover_3d < 5
и (ad_spend_3d_excl_today > 3000 или drr_3d_excl_today > 4)
и ad_spend_yesterday >= 1000
и ближайшая поставка отсутствует или через 5+ дней
```

Смысл `ad_spend_yesterday >= 1000`: если вчерашние траты уже ниже 1000 руб., считаем, что РК уже поправили или проблема перестала быть критичной, поэтому товар не нужно подсвечивать.

В сообщении обязательно выводятся:

- FBO;
- Обор-сть (3д);
- Траты (3д);
- Траты (вчера);
- ДРР (3д);
- Ближайшая поставка;
- название;
- маркетолог.

### ПРОВЕРИТЬ АКТИВНОСТЬ РК

```text
FBO >= 50
и rk_created = true
и ad_spend_3d < 3000
и turnover_3d > 30
и category not in CHECK_RK_EXCLUDED_CATEGORIES
```

Default временного исключения:

```text
Колготки
```

Блок в сообщении выводится последним и группируется:

```text
ПРОВЕРИТЬ АКТИВНОСТЬ РК:
• @Маркетолог
• • **Категория** / SKU: `N` / `article`, `article`
```

Категории жирные.

## Markdown-файл

Файл:

```text
pachca_wb_actions_YYYY-MM-DD.md
```

Секции:

1. `Условия`.
2. `НАСТРОИТЬ ЦЕНУ`.
3. `ВКЛЮЧИТЬ БЗО`.
4. `СОЗДАТЬ РК`.
5. `ВЫКЛЮЧИТЬ РК`.
6. `ПРОВЕРИТЬ АКТИВНОСТЬ РК`.

Табличные колонки:

- `Артикул ВБ`
- `Название товара`
- `Категория`
- `FBO`
- `Действие`
- `Цена / СПП`
- `Отзывы и рейтинг`
- `БЗО`
- `Заказы (7д)`
- `Наличие кампании РК`
- `Траты (3д)`
- `Оборачиваемость (3д)`
- `Траты РК (3д без сегодня)`
- `ДРР (3д без сегодня)`
- `Ближайшая поставка FBO`
- `Менеджер`
- `Маркетолог`

В Markdown названия действий не пишутся капсом внутри ячеек. Капс используется только в сообщении Пачки.

## Отправка в Пачку

`send_pachca_report.py`:

1. Запускает `build_action_report.py`.
2. Загружает Markdown-файл через Pachca `/uploads`.
3. Отправляет сообщение в `entity_type=discussion`.
4. Прикрепляет Markdown-файл.
5. Печатает JSON с `message_id`, `md`, `items`, `segments`.

Тред в этом боте не создается.

## Что менять при доработках

Если добавляется новый сегмент:

1. Добавить функцию условия.
2. Добавить сегмент в `build_segments()`.
3. Добавить формат строки в `message_item_line()` или отдельную grouped-функцию.
4. Добавить label в `md_action_label()`.
5. Проверить `table_row()`, если нужны новые метрики.
6. Обновить условия в Markdown и этот файл.

Если меняется общий источник БЗО, цены, менеджеров или маркетологов, проверить FBO-бот, потому что helpers общие.
