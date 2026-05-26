# Контекст WB Articles Report Notifications

Подпроект собирает ежедневный WB-отчет для сводки маркетолога и отправляет его в Пачку.

## Что отправляет

1. Сообщение в Пачку с ДРР с начала текущего месяца:
   - общий ДРР по marketplace `WB`;
   - ДРР по связке `IP / кабинет`.
2. Markdown-файл:
   - последние 30 дней по вчера включительно;
   - строки `date + cabinet + sku`;
   - таблицы разделены по месяцам, текущий месяц идет отдельной таблицей.
3. JSON-summary для GitHub Actions artifact.

## Расписание и ручной запуск

- GitHub Actions schedule: `0 6 * * *`, каждый день 09:00 МСК.
- Pachca command: `/отчет_уведомление`.
- Продовый чат: `39531378`.
- Тестовый чат: `39363429`.

## Главные файлы

- `build_wb_articles_marketer_report.py` - расчет SQL-данных, MTD-метрик, Markdown и сообщения.
- `send_pachca_report.py` - загрузка Markdown-файла и отправка сообщения в Пачку.
- `.github/workflows/wb-articles-report-notifications.yml` - GitHub Actions runner.
- `cloudflare/abcage_notification/src/index.js` - cron/command dispatcher.

## Источники данных

- `mp.mp_core__realtime_stocks_data` - текущий FBO, фильтр `FBO >= 10`.
- `mp.wb_core__funnel` - открытия карточек, корзины, заказы WB, выручка WB, выкупы.
- `mp.wb_core__campaign_stat_daily_sku` - показы, клики, корзины/заказы РК, траты РК.
- `mp.wb_core__card` и `mp.vw_mp_core__card_all` - артикул, название, категория, юрлицо/IP.
- `mp.mp_core__sales_plan` - план продаж, плановая цена, плановый ДРР.
- `mp.mp_core__realtime_finance` - выручка и маржа для расчетной маржи после РК.
- Google Sheet ответственных маркетологов через shared helper из `wb-fbo-supply-notifications`.

## Логика периода

По умолчанию `date_to = вчера` в `REPORT_TZ`, `date_from = date_to - 29 дней`.

Для корректных MTD-метрик SQL забирает данные с первого дня месяца `date_from`, а в Markdown выводятся только последние 30 дней. Cumulative-поля `orders_*_mtd`, прогнозы и выполнение плана обнуляются на границе месяца.
