# Контекст XWAY Limit Notifications

Подпроект еженедельного уведомления по проблемам биддера/XWAY.

## Расписание и запуск

- Плановый запуск: каждый понедельник в `08:30 МСК`.
- Продовый чат Пачки: `39531378`.
- Тестовый чат: `39363429`.
- Ручная команда в Пачке: `/биддер_уведомление`.
- GitHub Actions workflow: `.github/workflows/xway-limit-notifications.yml`.
- Cloudflare Worker: `cloudflare/abcage_notification`.

## Что отправляется

Одно сообщение в Пачку со сводкой по маркетологам и 4 файла:

1. `1. Проблемы: настройка лимитов и бюджетов.md`
2. `2. Проблемы: вылеты лимитов.md`
3. `3. Проблемы: Автоисключения Поиска.md`
4. `Инструкция: отчеты по проблемам лимитов.md`

## Период

По умолчанию берутся последние 3 дня до вчера по Москве:

```text
end = вчера
start = end - 2 дня
```

Можно переопределить через `REPORT_START` и `REPORT_END`.

## Источники

### XWAY

Используются прямые методы `https://am.xway.ru`, а не тяжелый `/api/pachka-report`:

- `GET /api/adv/shop/list?query=`
- `GET /api/adv/shop/{shop_id}/product/list-wo-stat`
- `GET /api/adv/shop/{shop_id}/product/list-stat`
- `GET /api/adv/shop/{shop_id}/product/{product_id}/stata`
- `POST /api/adv/shop/{shop_id}/product/{product_id}/campaign/{campaign_id}/status-pause-history`
- `GET /api/adv/shop/{shop_id}/product/{product_id}/campaign/{campaign_id}/retrieve-ac-exclude-rule`
- `GET /api/adv/shop/{shop_id}/product/{product_id}/campaign/{campaign_id}/normquery-stats`

XWAY авторизация передается через `XWAY_STORAGE_STATE_JSON`, `XWAY_STORAGE_STATE_BASE64`, `XWAY_COOKIE_HEADER` или `XWAY_SESSIONID`.

### ABCAGE Analyzer DB

В отличие от исходной локальной инструкции, финальный бот берет эти поля не из XWAY, а из ABCAGE Analyzer/MySQL:

- `Название товара`: `mp.wb_core__card.short_name/name`
- `Категория`: `mp.wb_core__card.object`
- `Остаток FBO`: последний срез `mp.mp_core__realtime_stocks_data.fbo_real`

Финальный фильтр для всех отчетов:

```text
Остаток FBO из БД > 10
```

### Маркетолог

Маркетолог берется из Google Sheet CSV:

```text
spreadsheet: 1STPnPgj8xSrvN-F3K96bDj_pmunCICHTjaj358pRaB4
gid: 1574673852
B = WB-артикул
H = тег маркетолога
```

## Отчеты

### 1. Настройка лимитов и бюджетов

Проверяются кампании в статусе `ACTIVE` или `PAUSED`.

Строка попадает в отчет, если по кампании:

- не настроен лимит расхода: `spend_limit_active` не true или `spend_limit <= 0`;
- или не настроено пополнение бюджета: `budget_rule_active` не true или `budget_limit <= 0`.

`FROZEN` исключается.

### 2. Вылеты лимитов

Проверяются `ACTIVE` и `PAUSED` кампании через `status-pause-history`.

Строка попадает в отчет, если причина неактивности:

- `limit` -> `лимит расходов`;
- `budget` -> `нехватка бюджета`;
- максимальный непрерывный инцидент по причине не меньше `4 ч`.

Строки агрегируются на уровне `товар + тип РК`.

### 3. Автоисключения Поиска

Проверяются только CPM кампании в статусе `ACTIVE` или `PAUSED`; CPC и FROZEN исключаются.

Кампания считается проблемной, если автоисключение не настроено:

- правило отсутствует;
- правило выключено;
- режим условий включен, но условий нет;
- прочий `configured=false`.

Дополнительные фильтры:

- расход кампании за период должен быть `> 0`;
- для `Единая ставка` должно быть `Кластеры с тратами за 3 дня > 0`.

Кластеры считаются через `campaignNormqueryStats`:

- `Кластеры с тратами`: `expense > 0` и `excluded != true`;
- `Зафиксированные кластеры`: `fixed = true`.

## Секреты GitHub

- `ABCAGE_ANALYZER_TOKEN`
- `XWAY_STORAGE_STATE_JSON`
- `PACHCA_TOKEN_XWAY_LIMITS`
- `PACHCA_CHAT_ID_XWAY_LIMITS`

Не коммитить storage state, Pachca token, `.env` и сгенерированные отчеты.
