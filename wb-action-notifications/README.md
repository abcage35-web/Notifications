# WB Action Notifications

Подпроект `/действия_уведомление`: сводный отчет по действиям для товаров WB.

Автоматические отправки по расписанию идут в продовый чат Пачки `36815841`.
Тестовые ручные отправки выполняются в чат `39363429` через input `pachca_chat_id`.

## Защита от пустых отчетов

- Остатки выбираются только из `mp='wb'`.
- Пустой или аномально неполный свежий срез заменяется предыдущим валидным срезом не старше одного дня.
- В сообщении всегда указывается дата использованного FBO-среза; fallback помечается явно.
- Если свежего валидного среза нет или карточки не сопоставились, сборка падает до обращения к Pachca API.
- Если источники валидны, но под условия не попало ни одного товара, отправка в Пачку пропускается.

## Логика действий

- `Цена: проверить цену`: FBO >= 50 и цена до СПП >= 80 000 руб.
- `БЗО: включить БЗО`: FBO >= 50, БЗО нет, отзывов <= 10, заказов за 7 дней <= 10.
- `РК: включить РК`: нет неархивной РК и FBO >= 50.
- `РК: проверить активность РК`: РК есть, траты (3д) < 3 000 руб., FBO >= 50, оборачиваемость > 30 дней; временно исключается категория `Колготки`.
- `РК: выключить РК`: РК есть, оборачиваемость за 3 полных дня < 5 дней, а траты РК за 3 полных дня > 3 000 руб. или ДРР за 3 полных дня > 4%; траты за вчера >= 1 000 руб.; ближайшая плановая поставка FBO через 5+ дней или отсутствует.

Для `выключить РК` окно 3д исключает сегодня.

## Ответственные

- Маркетолог берется по артикулу WB из таблицы ответственных маркетологов и используется в действиях по РК.
- Менеджер берется по артикулу WB из таблицы репрайсера и используется в действиях по цене и БЗО.
- Елена для БЗО резолвится через Pachca API `/users` и вставляется в сообщение как `<@user_id>`.

## Запуск

```bash
python send_pachca_report.py
```

Нужные env:

- `ABCAGE_ANALYZER_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PACHCA_TOKEN`
- `PACHCA_CHAT_ID`
- `REPORT_RUN_LABEL`
- `CHECK_RK_EXCLUDED_CATEGORIES` can override temporary excluded categories for `РК: проверить активность РК`, default is `Колготки`.
- `RK_DISABLE_YESTERDAY_SPEND_THRESHOLD` controls the minimum yesterday spend for `РК: выключить РК`, default is `1000`.
- `WB_STOCK_LOOKBACK_DAYS` controls the stock snapshot lookback, default is `7`.
- `WB_STOCK_MAX_AGE_DAYS` controls the maximum accepted snapshot age, default is `1`.
- `WB_STOCK_MIN_FBO_RATIO` controls the minimum FBO ratio to the previous valid day, default is `0.2`.
- `WB_STOCK_MIN_POSITIVE_SKU_RATIO` controls the minimum positive-SKU ratio to the previous valid day, default is `0.5`.

Проверка перед сборкой и отправкой:

```bash
python -m unittest -v test_stock_snapshot_guard.py
```
